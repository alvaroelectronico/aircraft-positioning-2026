"""Compiled decode kernels for ``iterated_greedy_vnd.py``.

The two decoders are the whole cost of a solve (the search around them is a
few percent), so their inner loops live here as array kernels compiled with
numba.  Each kernel is a line-for-line port of the dict-based decoder it
replaced — same arithmetic in the same order, same tie-breaking — so a decode
is byte-identical whether or not numba is installed; without numba the
kernels simply run as (much slower) Python.

Indexing: aircraft are ``0..R-1`` in instance order, positions ``0..P-1``;
aircraft r's job chain is the slice ``job_off[r]:job_off[r+1]`` of the flat
job arrays.  The solver prepares these arrays once per instance
(``IteratedGreedyVNDJobSolver._prepare``).
"""
from __future__ import annotations

import time

import numpy as np

try:
    from numba import njit, objmode, types
    from numba.typed import Dict
    HAVE_NUMBA = True
    _F8 = types.float64
    _K2 = types.UniTuple(types.float64, 2)
    _K5 = types.UniTuple(types.float64, 5)
except ImportError:                       # pragma: no cover - fallback path
    HAVE_NUMBA = False
    _F8 = _K2 = _K5 = None

    class Dict(dict):
        @staticmethod
        def empty(key_type=None, value_type=None):
            return {}

    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

@njit(cache=True)
def _bisect_right(a, x, lo, hi):
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


@njit(cache=True)
def _bisect_left(a, x, lo, hi):
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


@njit(cache=True)
def _sift_down(h, i, m):
    """Restore the min-heap property of h[:m] below index i."""
    x = h[i]
    while True:
        c = 2 * i + 1
        if c >= m:
            break
        if c + 1 < m and h[c + 1] < h[c]:
            c += 1
        if h[c] < x:
            h[i] = h[c]
            i = c
        else:
            break
    h[i] = x


@njit(cache=True)
def _heap_pop(h, m):
    """Pop the minimum of the heap h[:m]; the heap becomes h[:m-1]."""
    v = h[0]
    h[0] = h[m - 1]
    if m > 2:
        _sift_down(h, 0, m - 1)
    return v


@njit(cache=True)
def _less(lo1, hi1, k1, lo2, hi2, k2):
    """Tuple order (lo, hi, owner) of the Python decoder (owner by name rank)."""
    if lo1 != lo2:
        return lo1 < lo2
    if hi1 != hi2:
        return hi1 < hi2
    return k1 < k2


@njit(cache=True)
def metrics(L, finish, placed):
    """(makespan, total delay) over the placed aircraft, summed in aircraft
    order — the same float operations as the dict-building loop."""
    mk = 0.0
    td = 0.0
    for r in range(L.shape[0]):
        if placed[r]:
            f = finish[r]
            d = f - L[r]
            if d > 0.0:
                td += d
            if f > mk:
                mk = f
    return mk, td


# ----------------------------------------------------------------------
# zero-movement decoder (``_decode``)
# ----------------------------------------------------------------------

@njit(cache=True)
def scratch(R, P, mj):
    """Working buffers of the decoders, allocated once per kernel call and
    reused by every evaluation in it (R aircraft, P positions, at most mj
    jobs per aircraft): 0 members per position, 1 their counts, 2-4 forbidden
    bands (lo, hi, owner), 5 rear accesses, 6 their sorted copy, 7 candidate
    starts, 8 job offsets, 9-11 / 12-14 best / trial job times (start, finish,
    kappa), 15 positions in order, 16 a trial order, 17 an affected-position
    mask, 18 an all-True mask, 19 a same-members mask, 20 per-position
    "rear accesses changed" flags, 21 an all-False mask."""
    n2 = 2 * R + 2
    return (np.empty((P, R + 1), np.int64), np.zeros(P, np.int64),
            np.empty(n2, np.float64), np.empty(n2, np.float64), np.empty(n2, np.int64),
            np.empty(n2, np.float64), np.empty(n2, np.float64),
            np.empty(n2 * (5 + 5 * mj), np.float64), np.empty(mj, np.float64),
            np.empty(mj, np.float64), np.empty(mj, np.float64), np.empty(mj, np.int64),
            np.empty(mj, np.float64), np.empty(mj, np.float64), np.empty(mj, np.int64),
            np.empty(R + 1, np.int64), np.empty(R + 1, np.int64),
            np.zeros(P, np.bool_), np.ones(P, np.bool_), np.ones(P, np.bool_),
            np.zeros(P, np.bool_), np.zeros(P, np.bool_))


@njit(cache=True)
def max_jobs(job_off):
    mj = 1
    for r in range(job_off.shape[0] - 1):
        if job_off[r + 1] - job_off[r] > mj:
            mj = job_off[r + 1] - job_off[r]
    return mj


@njit(cache=True)
def decode_v2(order, order_pos, E, T, kind, rank, eps, band, start, pushers):
    """Zero-movement decode of the whole order (see ``decode_v2_from``)."""
    decode_v2_from(0, order, order_pos, E, T, kind, rank, eps, band, start, pushers,
                   scratch(E.shape[0], kind.shape[0], 1), E, 0.0, 0.0, np.inf)


@njit(cache=True)
def decode_v2_from(k0, order, order_pos, E, T, kind, rank, eps, band, start, pushers, scr,
                   L, wM, wD, bound):
    """Earliest-fit placement in priority order, every access kept in Mode A.

    Aircraft are placed one at a time; each gets the earliest start ``t``
    outside the *forbidden bands* induced by the aircraft already placed —
    the open intervals of start times that would put one of the two access
    instants of a blocking pair outside Mode A.  ``kind[p, p2]``: 0 free
    (positions do not block each other: free to overlap), 1 same position,
    2 ``p2`` is a front of ``p`` (we are the rear), 3 ``p2`` is a rear of
    ``p`` (we are the front).  ``band`` is the Mode-A clearance (0 or eta).

    Writes ``start[r]`` and ``pushers[r, r2]`` = 1 when r2's band moved r's
    start (the pusher tree the local search filters candidates with).

    Each aircraft's start depends only on the aircraft before it in the
    order, so a state that shares its first ``k0`` entries (aircraft and
    positions) with a decoded one keeps their starts: ``start`` must hold
    them, and placement resumes at ``k0``.

    With a finite ``bound`` (deadlines ``L``, weights ``wM``/``wD``) the
    placement stops and returns True as soon as the aircraft placed so far
    already price the state at ``bound`` or more: the makespan and the total
    delay only grow as aircraft are added and none finishes before E + T, so
    the full decode could not come out below ``bound`` (a neighbour priced
    against the objective to beat).  Returns False after a full decode.
    """
    n = order.shape[0]
    P = kind.shape[0]
    cut = bound < np.inf
    mk_p = 0.0                                    # makespan / total delay
    td_p = 0.0                                    # lower bounds so far
    if cut:
        for k in range(n):
            f = E[order[k]] + T[order[k]]
            if f > mk_p:
                mk_p = f
        for k in range(k0):
            r = order[k]
            f = start[r] + T[r]
            if f > mk_p:
                mk_p = f
            if f > L[r]:
                td_p += f - L[r]
    members = scr[0]                              # placed aircraft per position
    cnt = scr[1]
    for p in range(P):
        cnt[p] = 0
    for k in range(k0):
        p = order_pos[k]
        members[p, cnt[p]] = order[k]
        cnt[p] += 1
    lo = scr[2]                                   # forbidden bands of the
    hi = scr[3]                                   # aircraft being placed,
    ow = scr[4]                                   # with their owners
    for k in range(k0, n):
        r = order[k]
        p = order_pos[k]
        dur = T[r]
        m = 0
        for p2 in range(P):
            kd = kind[p, p2]
            if kd == 0:
                continue
            for q in range(cnt[p2]):
                r2 = members[p2, q]
                s2 = start[r2]
                f2 = s2 + T[r2]
                if kd == 1:
                    # Same position: the two stays may not overlap and must be
                    # separated by the tow time eps — our stay [t, t+dur]
                    # clashes with [s2, f2] unless t+dur <= s2-eps or t >= f2+eps.
                    lo[m] = s2 - dur - eps; hi[m] = f2 + eps; ow[m] = r2; m += 1
                elif kd == 2:
                    # We are the REAR.  Both our access instants stay in Mode A
                    # if our stay is entirely before the front (t+dur <= s2,
                    # touching allowed), entirely after it (t >= f2), or
                    # *encloses* it (t <= s2 and t+dur >= f2).  The bands are
                    # open, so boundary placements land exactly on the
                    # checker's vacant-front edge.
                    if dur >= (f2 - s2) + 2 * band - 1e-9:
                        # Long enough to enclose: two bands, and the gap between
                        # them is the enclosing start window (the nesting hole).
                        lo[m] = s2 - band - dur; hi[m] = f2 + band - dur; ow[m] = r2; m += 1
                        lo[m] = s2 - band; hi[m] = f2 + band; ow[m] = r2; m += 1
                    else:
                        # Too short to enclose: only before/after survive.
                        lo[m] = s2 - band - dur; hi[m] = f2 + band; ow[m] = r2; m += 1
                else:
                    # We are the FRONT: symmetric, but now the rear's fixed
                    # access instants (s2, f2) must stay in Mode A relative to
                    # our stay — the rear is before us, after us, or encloses us.
                    if dur <= (f2 - s2) - 2 * band + 1e-9:
                        lo[m] = s2 - dur - band; hi[m] = s2 + band; ow[m] = r2; m += 1
                        lo[m] = f2 - dur - band; hi[m] = f2 + band; ow[m] = r2; m += 1
                    else:
                        lo[m] = s2 - dur - band; hi[m] = f2 + band; ow[m] = r2; m += 1
        # Sort the bands by (lo, hi, owner name) — insertion sort, a few dozen
        # bands at most.
        for a in range(1, m):
            l0 = lo[a]; h0 = hi[a]; o0 = ow[a]
            b = a - 1
            while b >= 0 and _less(l0, h0, rank[o0], lo[b], hi[b], rank[ow[b]]):
                lo[b + 1] = lo[b]; hi[b + 1] = hi[b]; ow[b + 1] = ow[b]
                b -= 1
            lo[b + 1] = l0; hi[b + 1] = h0; ow[b + 1] = o0
        # Earliest-fit scan: from E[r], whenever t falls inside a band jump to
        # its end — which naturally lands t in the nesting hole between a pair
        # of bands when enclosing is the only option.  Sorted by `lo`, one pass
        # suffices: once t is at or left of a band's `lo` it is left of every
        # later band, and no band already passed can contain it again.
        t = E[r]
        for a in range(m):
            if lo[a] + 1e-7 >= t:
                break
            if t < hi[a] - 1e-7:
                t = hi[a]
                pushers[r, ow[a]] = 1
        start[r] = t
        members[p, cnt[p]] = r
        cnt[p] += 1
        if cut:
            f = t + dur
            if f > mk_p:
                mk_p = f
            if f > L[r]:
                td_p += f - L[r]
            if wM * mk_p + wD * td_p >= bound + 1e-6:
                return True
    return False


# ----------------------------------------------------------------------
# manoeuvre-aware decoder (``_decode_v3``)
# ----------------------------------------------------------------------

if HAVE_NUMBA:
    @njit(cache=True)
    def pyround(x, nd):
        """``round(x, nd)`` with CPython's result.  numba's ``round`` scales and
        rounds, which differs from CPython's correctly-rounded decimal result
        exactly at decimal ties (x = ...d5 at digit nd+1) and when x·10^nd
        exceeds float precision; those rare cases are handed to CPython."""
        # A multiple of 1/16 has at most 4 decimals, so it rounds to itself
        # (every start and objective of the benchmark is one).
        x16 = x * 16.0
        if x16 == np.floor(x16) and abs(x) < 1e12 and nd >= 4:
            return x
        y = x * 10.0 ** nd
        if abs(y) >= 4503599627370496.0 or abs(y - np.floor(y) - 0.5) < 1e-3:
            with objmode(r="float64"):
                r = round(x, nd)
            return r
        return round(x, nd)
else:                                     # pragma: no cover - fallback path
    pyround = round


@njit(cache=True)
def _isort(a):
    """In-place insertion sort: the few rear accesses of one front (numba's
    ``ndarray.sort`` allocates on every call, several times the cost)."""
    for i in range(1, a.shape[0]):
        v = a[i]
        k = i - 1
        while k >= 0 and a[k] > v:
            a[k + 1] = a[k]
            k -= 1
        a[k + 1] = v


@njit(cache=True)
def _round4(x):
    return pyround(x, 4)


@njit(cache=True)
def sim_front(j0, j1, job_dur, job_int, s_start, acc, stretch, eta, delta, mu,
              js, jf, jk):
    """Forward-simulate one front aircraft (jobs ``j0:j1``) from ``s_start``
    against the sorted rear access instants ``acc``, with ``stretch`` of idle
    before its last job (a minimum gap; accesses inside it are Mode B).

    Each access is classified against the laid-out jobs:
      * Mode C — strictly inside an interruptible job interior; the job is
        extended by ``delta`` (kappa fixpoint per job).
      * Mode B — routed through an inter-job *gap* (no job extension), sized
        ``>= mu * (#accesses in it)``.  A gap is opened after job j for the
        accesses just past its end when that is cheaper than Mode C (within
        ``delta`` of the end) or when the next job is non-interruptible (the
        access cannot be absorbed and must pass through a gap).
      * Mode A — outside the stay; free.
    Boundaries follow the checker's closed semantics: an access exactly at the
    stay start or finish is Mode A, one exactly at a job end is Mode B through
    the gap that follows it, and a gap opens at the job end nearest to the
    access.  Infeasible if an access lands in a non-interruptible job
    interior or in a job's eta-margin.

    Writes job starts / finishes / kappas into ``js``/``jf``/``jk`` (from
    index 0).  Returns (finish, mov_events, feasible); movements = 2·events.
    """
    m = acc.shape[0]
    # Accesses are consumed in time order, so the unclassified ones are always
    # a suffix acc[i:] lying after the cursor; counting and routing are
    # bisections on that suffix.  An access at or before the stay start is
    # Mode A (the front is not there yet, or is just entering its slot).
    i = _bisect_right(acc, s_start + 1e-9, 0, m)
    mov = 0
    t = s_start                                   # start of the next job
    n = j1 - j0
    for j in range(n):
        D = job_dur[j0 + j]
        # An access in the eta-margin at the job's start is neither cleanly
        # outside nor cleanly inside: the checker would reject it.
        if i < m and acc[i] < t + eta - 1e-9:
            return 0.0, 0, False
        # Mode-C count via a fixpoint: each interior access lengthens the job
        # by delta, which widens the interior and can pull in further accesses.
        kappa = 0
        f_j = t + D
        while True:
            f_j = t + D + delta * kappa
            c = _bisect_right(acc, f_j - eta + 1e-9, i, m) - i
            if c == kappa:
                break
            kappa = c
        # A Mode-C interruption is only legal on an interruptible job.
        if kappa > 0 and not job_int[j0 + j]:
            return 0.0, 0, False
        i += kappa                                # consume the Mode-C accesses
        # Same eta-margin rule at the job's end.
        if i < m and acc[i] < f_j - 1e-9:
            return 0.0, 0, False
        mov += kappa
        js[j] = t; jf[j] = f_j; jk[j] = kappa
        t = f_j
        # Mode-B gap before the next job.
        if j < n - 1:
            if not job_int[j0 + j + 1]:
                window = job_dur[j0 + j + 1]
            else:
                window = delta
            g = stretch if j == n - 2 else 0.0    # the search-owned idle
            # The gap is closed at its start (an access exactly at f_j goes
            # through it) and the window is open at its end (an access at the
            # NEXT job's end is routed at the next boundary).
            k = max(_bisect_left(acc, f_j + window - 1e-9, i, m),
                    _bisect_right(acc, f_j + g + 1e-9, i, m)) - i
            s_next = f_j + g
            if k:
                # The gap ends past the last routed access and absorbs mu per
                # access; widening it may enclose further accesses, which are
                # then also Mode B — iterate to a fixpoint.
                s_next = max(s_next, acc[i + k - 1], f_j + mu * k)
                while True:
                    k2 = _bisect_right(acc, s_next + 1e-9, i, m) - i
                    if k2 <= k:
                        break
                    k = k2
                    s_next = max(s_next, acc[i + k - 1], f_j + mu * k)
                i += k
                mov += k
            t = s_next
    # Any access still unclassified strictly inside the stay is an
    # unrepresentable boundary / zero-gap case: the checker would reject it.
    if i < m and s_start + eta - 1e-9 <= acc[i] <= t - eta + 1e-9:
        return 0.0, 0, False
    return t, mov, True


@njit(cache=True)
def place_front(j0, j1, job_dur, job_int, T0, L, lower, rear_acc, stretch,
                eta, delta, mu, wM, wD, wS, scr):
    """Minimum-cost feasible start (>= ``lower``) of one front aircraft whose
    rears' access instants ``rear_acc`` are fixed.  The chosen job times land
    in the scratch's best-job buffers.  Returns (start, finish, mov_events).
    """
    bjs = scr[9]; bjf = scr[10]; bjk = scr[11]
    tjs = scr[12]; tjf = scr[13]; tjk = scr[14]
    T = T0 + stretch
    n = j1 - j0
    na = rear_acc.shape[0]
    # prefix[j] = work-time offset of job j's start from the aircraft start,
    # ignoring delta extensions (a seed; sim_front recomputes exact times).
    prefix = scr[8]
    a = 0.0
    for k in range(n):
        if k == n - 1:
            a += stretch
        prefix[k] = a
        a += job_dur[j0 + k]
    n_int = 0
    for k in range(n):
        if job_int[j0 + k]:
            n_int += 1
    # Candidate starts: only those "interesting" w.r.t. some rear access tau —
    # keeping tau in Mode A, or aligning a job interior / job end on tau to
    # invite a cheap Mode C / Mode B.  `lower` and the zero-movement options
    # are always present, so the choice is never worse than a Mode-A schedule.
    # Rounded to 4 decimals so near-equal starts collapse.
    raw = scr[7]
    m = 0
    lo = lower - 1e-9
    for q in range(na):
        tau = rear_acc[q]
        # Zero-movement: the whole stay before tau (finish at tau or eta
        # before), after it (start at tau or eta after), or nested (start at
        # tau-eta-T); the band-tight tau-T and tau use the vacant-front
        # semantics (touching allowed at both edges).
        for c in (tau - T, tau - eta - T, tau - eta, tau, tau + eta):
            if lo <= c:
                raw[m] = c; m += 1
        for k in range(n):
            D = job_dur[j0 + k]
            t_pj = tau - prefix[k]
            # Mode-C alignment: job k's interior straddles tau (just after its
            # start, just before its end, or at its midpoint) — interruptible
            # jobs only.
            if job_int[j0 + k]:
                for c in (t_pj - eta, t_pj - D + eta, t_pj - D / 2.0):
                    if lo <= c:
                        raw[m] = c; m += 1
            # Mode-B alignment: job k ends just before tau, so tau falls into
            # the gap opened after it, with no delta extension.
            for c in (t_pj - D, t_pj - D - eta):
                if lo <= c:
                    raw[m] = c; m += 1
    # A min-heap, not a sort: the scan below usually stops after a handful of
    # candidates, so only those are ever extracted.
    for i in range(m // 2 - 1, -1, -1):
        _sift_down(raw, i, m)
    acc = scr[6][:na]
    acc[:] = rear_acc
    _isort(acc)
    # Two unrounded extras: `lower`, and the guaranteed-feasible fallback
    # (start after every rear access).
    sp0 = lower
    sp1 = max(lower, acc[na - 1] + eta) if na > 0 else lower
    # Price the candidates in increasing start by simulation; cost = the
    # aircraft's local objective (weighted finish + delay + 2 movements per
    # event).  The finish is >= s + T, so wM*(s+T) + wD*max(0, s+T-L) bounds
    # every later candidate's cost from below: once it reaches the best cost
    # nothing later can win (exact).  Rounding is monotone, so the rounded
    # candidates come out of the sorted raw ones in order and are rounded only
    # as the scan reaches them (it usually stops after a handful); merged with
    # the two extras and deduplicated, the scan visits exactly the sorted set
    # of distinct starts.
    best_cost = 0.0
    best_s = 0.0
    best_f = 0.0
    best_mov = 0
    have = False
    hm = m                                      # raw candidates left in the heap
    isp = 0                                     # next extra (0: sp0, 1: sp1, 2: none)
    nxt_r = _round4(_heap_pop(raw, hm)) if hm > 0 else 0.0
    have_r = hm > 0
    if hm > 0:
        hm -= 1
    last = 0.0
    first = True
    while have_r or isp < 2:
        sp = sp0 if isp == 0 else sp1
        if have_r and (isp >= 2 or nxt_r <= sp):
            s = nxt_r
            if hm > 0:
                nxt_r = _round4(_heap_pop(raw, hm))
                hm -= 1
            else:
                have_r = False
        else:
            s = sp
            isp += 1
        if not first and s == last:
            continue
        first = False
        last = s
        if have:
            f_lb = s + T
            if wM * f_lb + wD * max(0.0, f_lb - L) >= best_cost - 1e-9:
                break
        f_r, mov, ok = sim_front(j0, j1, job_dur, job_int, s, acc, stretch,
                                 eta, delta, mu, tjs, tjf, tjk)
        if not ok:
            continue
        delay = max(0.0, f_r - L)
        cost = wM * f_r + wD * delay + wS * (2 * mov)
        if not have or cost < best_cost - 1e-9:
            have = True
            best_cost = cost; best_s = s; best_f = f_r; best_mov = mov
            for k in range(n):
                bjs[k] = tjs[k]; bjf[k] = tjf[k]; bjk[k] = tjk[k]
    # `lower` with no rears, or the fallback, is always feasible.
    return best_s, best_f, best_mov


@njit(cache=True)
def decode_v3(order, order_pos, sh_d, sh_g, E, L, T, job_off, job_dur, job_int,
              pos_by_depth, rears_of, n_rears, eta, eps, delta, mu, wM, wD, wS,
              start, finish, mov_ev, js, jf, jk, placed):
    """Manoeuvre-aware decode of the whole state (see ``decode_v3_from``)."""
    scr = scratch(E.shape[0], pos_by_depth.shape[0], max_jobs(job_off))
    decode_v3_from(scr[18], scr[21], start, finish, mov_ev,
                   js, jf, jk, sh_d, sh_g, order, order_pos, sh_d, sh_g, E, L, T, job_off,
                   job_dur, job_int, pos_by_depth, rears_of, n_rears, eta, eps,
                   delta, mu, wM, wD, wS, start, finish, mov_ev, js, jf, jk, placed, scr,
                   np.inf)


@njit(cache=True)
def decode_v3_from(aff, same, b_start, b_finish, b_mov, b_js, b_jf, b_jk, b_shd, b_shg,
                   order, order_pos, sh_d, sh_g, E, L, T, job_off, job_dur, job_int,
                   pos_by_depth, rears_of, n_rears, eta, eps, delta, mu, wM, wD, wS,
                   start, finish, mov_ev, js, jf, jk, placed, scr, bound):
    """Manoeuvre-aware decode.  Positions are scheduled DEEPEST-REAR FIRST,
    so by the time a front is laid out every rear it blocks is placed and its
    access instants are known constants; each front then takes its
    minimum-cost start (``place_front``).  Within a position, aircraft follow
    the priority order, separated by the tow time eps.  ``sh_d``/``sh_g`` is
    the search-owned shift (start delay, stretch before the last job).

    A position's schedule depends only on its own members and on its rears,
    so a position with ``aff[p]`` False — same members, same order, same
    shifts as a decoded base state, and no affected rear — is copied from the
    base arrays ``b_*`` instead of being laid out again.  Finer, inside an
    affected position: an aircraft's placement depends only on the access
    instants of the rears, the previous member's finish and its own shift,
    so where the members are the base's (``same[p]``), no rear position's
    accesses changed, the previous member came out unchanged and the shift is
    the base's, the aircraft is copied too.  A position whose members all
    come out at the base's stays leaves its fronts' inputs unchanged, which
    stops the cascade of an inconsequential move.

    Every aircraft's schedule is final once placed, and the makespan, the
    total delay and the movement count only grow as aircraft are added (none
    finishes before E + T): with a finite ``bound`` the decode stops and
    returns True as soon as the aircraft placed so far price the state at
    ``bound`` or more.  Returns False after a full decode.
    """
    n = order.shape[0]
    P = pos_by_depth.shape[0]
    members = scr[0]
    cnt = scr[1]
    for p in range(P):
        cnt[p] = 0
    cut = bound < np.inf
    mk_p = 0.0                                    # objective lower bound so far:
    td_p = 0.0                                    # makespan, total delay,
    ev_p = 0                                      # movement events
    for k in range(n):
        p = order_pos[k]
        members[p, cnt[p]] = order[k]
        cnt[p] += 1
        f = E[order[k]] + T[order[k]]
        if f > mk_p:
            mk_p = f
    bjs = scr[9]; bjf = scr[10]; bjk = scr[11]
    acc = scr[5]
    acc_changed = scr[20]
    for pi in range(P):
        p = pos_by_depth[pi]
        if not aff[p]:
            for q in range(cnt[p]):
                r = members[p, q]
                start[r] = b_start[r]; finish[r] = b_finish[r]; mov_ev[r] = b_mov[r]
                for j in range(job_off[r], job_off[r + 1]):
                    js[j] = b_js[j]; jf[j] = b_jf[j]; jk[j] = b_jk[j]
                placed[r] = True
                if cut:
                    f = finish[r]
                    if f > mk_p:
                        mk_p = f
                    if f > L[r]:
                        td_p += f - L[r]
                    ev_p += mov_ev[r]
            acc_changed[p] = False
            if cut and wM * mk_p + wD * td_p + wS * (2 * ev_p) >= bound + 1e-6:
                return True
            continue
        reuse = same[p]
        for x in range(n_rears[p]):
            if acc_changed[rears_of[p, x]]:
                reuse = False
        any_changed = not same[p]
        prev_same = True
        have_prev = False
        prev_f = 0.0
        for q in range(cnt[p]):
            r = members[p, q]
            if reuse and prev_same and sh_d[r] == b_shd[r] and sh_g[r] == b_shg[r]:
                start[r] = b_start[r]; finish[r] = b_finish[r]; mov_ev[r] = b_mov[r]
                for j in range(job_off[r], job_off[r + 1]):
                    js[j] = b_js[j]; jf[j] = b_jf[j]; jk[j] = b_jk[j]
                placed[r] = True
                have_prev = True
                prev_f = b_finish[r]
                if cut:
                    if prev_f > mk_p:
                        mk_p = prev_f
                    if prev_f > L[r]:
                        td_p += prev_f - L[r]
                    ev_p += mov_ev[r]
                    if wM * mk_p + wD * td_p + wS * (2 * ev_p) >= bound + 1e-6:
                        return True
                continue
            # Earliest start: E[r], past the previous same-position aircraft
            # by eps, plus the search-owned delay.
            lower = E[r]
            if have_prev:
                lower = max(lower, prev_f + eps)
            lower += sh_d[r]
            # Access instants (entry and exit) of every placed rear this
            # position blocks — the events the front must classify A / B / C.
            na = 0
            for x in range(n_rears[p]):
                pr = rears_of[p, x]
                for y in range(cnt[pr]):
                    a = members[pr, y]
                    if placed[a]:
                        acc[na] = start[a]; acc[na + 1] = finish[a]; na += 2
            j0 = job_off[r]; j1 = job_off[r + 1]
            s, f, mv = place_front(j0, j1, job_dur, job_int, T[r], L[r], lower,
                                   acc[:na], sh_g[r], eta, delta, mu, wM, wD, wS, scr)
            start[r] = s; finish[r] = f; mov_ev[r] = mv; placed[r] = True
            for k in range(j1 - j0):
                js[j0 + k] = bjs[k]; jf[j0 + k] = bjf[k]; jk[j0 + k] = bjk[k]
            have_prev = True
            prev_f = f
            prev_same = s == b_start[r] and f == b_finish[r]
            if not prev_same:
                any_changed = True
            if cut:
                if f > mk_p:
                    mk_p = f
                if f > L[r]:
                    td_p += f - L[r]
                ev_p += mv
                if wM * mk_p + wD * td_p + wS * (2 * ev_p) >= bound + 1e-6:
                    return True
        acc_changed[p] = any_changed
    return False


# ----------------------------------------------------------------------
# neighbourhood scans (``_local_search`` / ``_perturb`` reinsertion)
# ----------------------------------------------------------------------
# One call prices a whole neighbourhood instead of one neighbour per Python
# round-trip.  ``inst`` = (E, L, T, kind, rank, job_off, job_dur, job_int,
# pos_by_depth, rears_of, n_rears, dep); ``prm`` = [eps, band, eta, delta, mu,
# wM, wD, wS]; ``apos[r]`` = position index of aircraft r.  Objectives are
# the solver's ``round(obj, 6)``, so comparisons match the Python search.
# Every neighbour is priced incrementally from the decoded base state (the
# current one, or the kept order of a reinsertion): from the first changed
# order entry under the zero-movement decoder, only the positions it touches
# and those in front of them under the manoeuvre decoder — the same decode,
# without recomputing what cannot change.

@njit(cache=True)
def objective(v3, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push, scr):
    """``_objective(_decode(...))`` of one state, in preallocated workspace
    (``ws_f`` float [4, max(R, J)], ``ws_i`` int [2, max(R, J)], ``ws_b``
    bool [R], ``push`` uint8 [R, R])."""
    E, L, T, kind, rank, job_off, job_dur, job_int, pos_by_depth, rears_of, n_rears, dep = inst
    eps, band, eta, delta, mu, wM, wD, wS = prm[0], prm[1], prm[2], prm[3], prm[4], prm[5], prm[6], prm[7]
    R = E.shape[0]
    n = order.shape[0]
    op = scr[15][:n]
    for k in range(n):
        op[k] = apos[order[k]]
    start = ws_f[0, :R]
    finish = ws_f[1, :R]
    placed = ws_b
    for r in range(R):
        placed[r] = False
    if not v3:
        decode_v2_from(0, order, op, E, T, kind, rank, eps, band, start, push, scr,
                       L, wM, wD, np.inf)
        for k in range(n):
            r = order[k]
            finish[r] = start[r] + T[r]
            placed[r] = True
        mk, td = metrics(L, finish, placed)
        return pyround(wM * mk + wD * td, 6)
    J = job_dur.shape[0]
    mov_ev = ws_i[0, :R]
    for r in range(R):
        mov_ev[r] = 0
    decode_v3_from(scr[18], scr[21], start, finish, mov_ev, ws_f[2, :J], ws_f[3, :J],
                   ws_i[1, :J], sh_d, sh_g, order, op, sh_d, sh_g, E, L, T, job_off,
                   job_dur, job_int,
                   pos_by_depth, rears_of, n_rears, eta, eps, delta, mu, wM, wD, wS,
                   start, finish, mov_ev, ws_f[2, :J], ws_f[3, :J], ws_i[1, :J], placed, scr,
                   np.inf)
    mk, td = metrics(L, finish, placed)
    ev = 0
    for r in range(R):
        ev += mov_ev[r]
    return pyround(wM * mk + wD * td + wS * (2 * ev), 6)


@njit(cache=True)
def _same(P, a, b, out):
    """Positions whose members (and their order) are the base's: all but a
    and b (b < 0: none)."""
    for x in range(P):
        out[x] = x != a and x != b
    return out


@njit(cache=True)
def objective_from(v3, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push,
                   scr, base, k0, aff, same, bound):
    """``objective`` of a state that differs from the decoded ``base`` state
    (``base`` = start, finish, mov_ev, js, jf, jk, shifts of it) only from
    order entry ``k0`` on (zero-movement) / only at the positions ``aff``,
    with the base's members at the positions ``same`` (manoeuvre).  Returns
    inf, without finishing the decode, once the state is priced at ``bound``
    or more — pass the objective to beat, or inf when the decoded schedule
    itself is wanted."""
    E, L, T, kind, rank, job_off, job_dur, job_int, pos_by_depth, rears_of, n_rears, dep = inst
    eps, band, eta, delta, mu, wM, wD, wS = prm[0], prm[1], prm[2], prm[3], prm[4], prm[5], prm[6], prm[7]
    b_start, b_finish, b_mov, b_js, b_jf, b_jk, b_shd, b_shg = base
    R = E.shape[0]
    n = order.shape[0]
    op = scr[15][:n]
    for k in range(n):
        op[k] = apos[order[k]]
    start = ws_f[0, :R]
    finish = ws_f[1, :R]
    placed = ws_b
    for r in range(R):
        placed[r] = False
    if not v3:
        for k in range(k0):
            r = order[k]
            start[r] = b_start[r]
        if decode_v2_from(k0, order, op, E, T, kind, rank, eps, band, start, push, scr,
                          L, wM, wD, bound):
            return np.inf
        for k in range(n):
            r = order[k]
            finish[r] = start[r] + T[r]
            placed[r] = True
        mk, td = metrics(L, finish, placed)
        return pyround(wM * mk + wD * td, 6)
    J = job_dur.shape[0]
    mov_ev = ws_i[0, :R]
    for r in range(R):
        mov_ev[r] = 0
    if decode_v3_from(aff, same, b_start, b_finish, b_mov, b_js, b_jf, b_jk, b_shd, b_shg,
                      order, op, sh_d, sh_g, E, L, T, job_off, job_dur, job_int,
                      pos_by_depth, rears_of, n_rears, eta, eps, delta, mu, wM, wD, wS,
                      start, finish, mov_ev, ws_f[2, :J], ws_f[3, :J], ws_i[1, :J], placed,
                      scr, bound):
        return np.inf
    mk, td = metrics(L, finish, placed)
    ev = 0
    for r in range(R):
        ev += mov_ev[r]
    return pyround(wM * mk + wD * td + wS * (2 * ev), 6)


@njit(cache=True)
def _base(ws_f, ws_i, R, J, sh_d, sh_g):
    """Copy of the state just decoded into the workspace (the base the
    neighbours are priced from), with its shifts."""
    return (ws_f[0, :R].copy(), ws_f[1, :R].copy(), ws_i[0, :R].copy(),
            ws_f[2, :J].copy(), ws_f[3, :J].copy(), ws_i[1, :J].copy(),
            sh_d.copy(), sh_g.copy())


@njit(cache=True)
def _affected(dep, a, b, out):
    """Positions whose manoeuvre-decoder schedule can change when positions
    a and b (b < 0: none) change: themselves and every position that has one
    of them among its rears, transitively."""
    P = dep.shape[0]
    for x in range(P):
        out[x] = x == a or dep[x, a] or (b >= 0 and (x == b or dep[x, b]))
    return out


@njit(cache=True)
def _workspace(R, J, P, mj):
    m = max(R, J)
    return (np.empty((4, m), np.float64), np.empty((2, m), np.int64),
            np.empty(R, np.bool_), np.zeros((R, R), np.uint8), scratch(R, P, mj))


@njit(cache=True)
def order_slots(v3, r, rest, apos, kind):
    """``_order_slots``: one insertion slot per distinct-decode class of r in
    ``rest`` — delimited by same-position aircraft (and, under the
    zero-movement decoder, aircraft in blocking conflict)."""
    p = apos[r]
    n = rest.shape[0]
    slots = np.empty(n + 1, np.int64)
    m = 0
    for i in range(n):
        pq = apos[rest[i]]
        if v3:
            hit = pq == p
        else:
            hit = pq == p or kind[p, pq] == 2 or kind[p, pq] == 3
        if hit:
            if m == 0:
                slots[m] = i; m += 1
            slots[m] = i + 1; m += 1
    if m == 0:
        slots[m] = n; m += 1
    return slots[:m]


@njit(cache=True)
def _insert(rest, slot, r, buf):
    n = rest.shape[0]
    out = buf[:n + 1]
    for k in range(slot):
        out[k] = rest[k]
    out[slot] = r
    for k in range(slot, n):
        out[k + 1] = rest[k]
    return out


@njit(cache=True)
def _moves_of(v3, r, apos, order, at, sh_d, sh_g, cur, inst, prm, P,
              ws_f, ws_i, ws_b, push, scr, base):
    """The first improving move of aircraft r, priced against the decoded
    ``base`` of the state (``at``: index of each aircraft in ``order``) and
    scanned in a fixed order — (1) reassign to each other position, (2)
    relocate to one slot per distinct-decode class, (3) swap positions with
    each aircraft on another position.  Returns (move, arg, obj, n_evals):
    move 0 none, 1 reassign to position ``arg``, 2 relocate to slot ``arg`` of
    the order without r, 3 swap with aircraft ``arg``.  ``apos`` is left
    unchanged."""
    kind = inst[3]
    dep = inst[11]
    R = inst[0].shape[0]
    n = order.shape[0]
    nev = 0
    p0 = apos[r]
    for p in range(P):
        if p == p0:
            continue
        apos[r] = p
        o = objective_from(v3, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                           push, scr, base, at[r], _affected(dep, p0, p, scr[17]),
                           _same(P, p0, p, scr[19]), cur)
        nev += 1
        if o < cur - 1e-9:
            apos[r] = p0
            return 1, p, o, nev
    apos[r] = p0
    rest = np.empty(n - 1, np.int64)
    i0 = at[r]
    m = 0
    for k in range(n):
        if order[k] != r:
            rest[m] = order[k]; m += 1
    slots = order_slots(v3, r, rest, apos, kind)
    aff0 = _affected(dep, p0, -1, scr[17])
    same0 = _same(P, p0, -1, scr[19])
    for s in range(slots.shape[0]):
        slot = slots[s]
        if slot == i0:
            continue
        o = objective_from(v3, _insert(rest, slot, r, scr[16]), apos, sh_d, sh_g, inst, prm,
                           ws_f, ws_i, ws_b, push, scr, base, min(i0, slot), aff0, same0,
                           cur)
        nev += 1
        if o < cur - 1e-9:
            return 2, slot, o, nev
    for q in range(R):
        if q == r or apos[q] == p0:
            continue
        pq = apos[q]
        apos[r] = pq; apos[q] = p0
        o = objective_from(v3, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                           push, scr, base, min(at[r], at[q]), _affected(dep, p0, pq, scr[17]),
                           _same(P, p0, pq, scr[19]), cur)
        nev += 1
        apos[q] = pq; apos[r] = p0
        if o < cur - 1e-9:
            return 3, q, o, nev
    return 0, 0, cur, nev


@njit(cache=True)
def best_insert(v3, r, apos, kept, sh_d, sh_g, inst, prm, P):
    """``_perturb`` reinsertion of r: the best (position, slot) over every
    position and one slot per distinct-decode class, first one on ties.
    Returns (position, slot, obj, n_evals); ``apos`` is left unchanged."""
    E = inst[0]
    kind = inst[3]
    job_dur = inst[6]
    dep = inst[11]
    R = E.shape[0]
    J = job_dur.shape[0]
    ws_f, ws_i, ws_b, push, scr = _workspace(R, J, inst[8].shape[0], max_jobs(inst[5]))
    objective(v3, kept, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push, scr)
    base = _base(ws_f, ws_i, R, J, sh_d, sh_g)
    p0 = apos[r]
    best_o = 0.0
    best_p = -1
    best_s = -1
    nev = 0
    for p in range(P):
        apos[r] = p
        slots = order_slots(v3, r, kept, apos, kind)
        aff = _affected(dep, p, -1, scr[17])
        same = _same(P, p, -1, scr[19])
        for s in range(slots.shape[0]):
            slot = slots[s]
            o = objective_from(v3, _insert(kept, slot, r, scr[16]), apos, sh_d, sh_g, inst, prm,
                               ws_f, ws_i, ws_b, push, scr, base, slot, aff, same,
                               best_o if best_p >= 0 else np.inf)
            nev += 1
            if best_p < 0 or o < best_o:
                best_o = o; best_p = p; best_s = slot
    apos[r] = p0
    return best_p, best_s, best_o, nev


# ----------------------------------------------------------------------
# align polish (``_align``, Attempt 17)
# ----------------------------------------------------------------------

if HAVE_NUMBA:
    @njit(cache=True)
    def _now():
        with objmode(t="float64"):
            t = time.perf_counter()
        return t
else:                                     # pragma: no cover - fallback path
    def _now():
        return time.perf_counter()


@njit(cache=True)
def scan_moves(v3, cands, apos, order, sh_d, sh_g, cur, inst, prm, P, deadline):
    """One pass of ``_local_search``: the moves (``_moves_of``) of each
    aircraft of ``cands`` in turn, against a single decode of the state, until
    one improves.  Returns (j, move, arg, obj, n_evals): j the index in ``cands``
    of the improving aircraft, or of the first one not scanned because
    ``deadline`` (perf_counter) passed (move 0), or len(cands) when none
    improves."""
    R = inst[0].shape[0]
    J = inst[6].shape[0]
    ws_f, ws_i, ws_b, push, scr = _workspace(R, J, inst[8].shape[0], max_jobs(inst[5]))
    n = order.shape[0]
    at = np.full(R, n, np.int64)
    for k in range(n):
        at[order[k]] = k
    objective(v3, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push, scr)
    base = _base(ws_f, ws_i, R, J, sh_d, sh_g)
    nev = 0
    for j in range(cands.shape[0]):
        if _now() >= deadline:
            return j, 0, 0, cur, nev
        move, arg, o, ne = _moves_of(v3, cands[j], apos, order, at, sh_d, sh_g, cur, inst,
                                     prm, P, ws_f, ws_i, ws_b, push, scr, base)
        nev += ne
        if move != 0:
            return j, move, arg, o, nev
    return cands.shape[0], 0, 0, cur, nev


@njit(cache=True)
def _msort_xy(idx, tmp, x, y):
    """Stable bottom-up merge sort of ``idx`` by (x[i], y[i]) — no allocation
    (``tmp`` as long as ``idx``)."""
    n = idx.shape[0]
    src = idx
    dst = tmp
    w = 1
    while w < n:
        lo = 0
        while lo < n:
            mid = min(lo + w, n)
            hi = min(lo + 2 * w, n)
            i = lo; j = mid; o = lo
            while i < mid and j < hi:
                a = src[i]; b = src[j]
                if x[b] < x[a] or (x[b] == x[a] and y[b] < y[a]):
                    dst[o] = b; j += 1
                else:
                    dst[o] = a; i += 1
                o += 1
            while i < mid:
                dst[o] = src[i]; i += 1; o += 1
            while j < hi:
                dst[o] = src[j]; j += 1; o += 1
            lo += 2 * w
        src, dst = dst, src
        w *= 2
    if src is not idx:
        for i in range(n):
            idx[i] = src[i]


@njit(cache=True)
def _nearest(key, m, out):
    """Indices of the ``m`` smallest keys, smallest first, the lowest index on
    ties — the first ``m`` of a stable argsort.  ``key`` is consumed."""
    for i in range(m):
        best = -1
        for j in range(key.shape[0]):
            if key[j] == np.inf:
                continue
            if best < 0 or key[j] < key[best]:
                best = j
        out[i] = best
        key[best] = np.inf
    return out[:m]


@njit(cache=True)
def align_proposals(r, apos, sh_d, sh_g, start, finish, js, jf, job_off, job_dur,
                    fronts, n_fronts, rears, n_rears):
    """Shifts of rear r that put its exit (by stretch or by delay) or its
    entry (by delay) exactly on a boundary of a front aircraft r interacts
    with, in the decoded schedule (``start``/``finish``/``js``/``jf``), plus
    the reset to no shift.  The front aircraft are those at a position
    blocking r whose stay overlaps r's, and on each such position the last
    one before r's stay and the first one after it — an aligned exit or entry
    can only matter against those (all of them would be hundreds of far-off
    boundaries at scale).  Their boundaries: stay start and finish, job starts
    and ends, and the job ends the front would have had if not pushed (jobs
    tight from its start) — a rear exit landing there is what lets the front
    run tight, and that boundary only appears once it does.  Returned in the
    order of the sorted proposal set, rounded to 6 decimals, without
    negatives and without the current shift.

    The same selection on the positions r blocks adds the rear aircraft's
    entry and exit: a front that stays until its rear leaves (finish = the
    rear's exit, Mode A at the closed boundary) is how the optima wrap a
    wave of aircraft along a chain without manoeuvres."""
    R = start.shape[0]
    p = apos[r]
    s_r = start[r]
    f_r = finish[r]
    flags = np.zeros(2 * R, np.bool_)
    use = flags[:R]
    for x in range(n_fronts[p]):
        fp = fronts[p, x]
        before = -1
        after = -1
        for a in range(R):
            if a == r or apos[a] != fp:
                continue
            if start[a] <= f_r and s_r <= finish[a]:
                use[a] = True
            elif finish[a] < s_r:
                if before < 0 or finish[a] > finish[before]:
                    before = a
            elif after < 0 or start[a] < start[after]:
                after = a
        if before >= 0:
            use[before] = True
        if after >= 0:
            use[after] = True
    use_r = flags[R:]
    for x in range(n_rears[p]):
        rp = rears[p, x]
        before = -1
        after = -1
        for a in range(R):
            if a == r or apos[a] != rp:
                continue
            if start[a] <= f_r and s_r <= finish[a]:
                use_r[a] = True
            elif finish[a] < s_r:
                if before < 0 or finish[a] > finish[before]:
                    before = a
            elif after < 0 or start[a] < start[after]:
                after = a
        if before >= 0:
            use_r[before] = True
        if after >= 0:
            use_r[after] = True
    nb = 0
    for a in range(R):
        if use[a]:
            nb += 2 + 3 * (job_off[a + 1] - job_off[a])
        if use_r[a]:
            nb += 2
    can_stretch = job_off[r + 1] - job_off[r] > 1
    k = 1 + nb * (3 if can_stretch else 2)
    fbuf = np.empty(nb + 4 * k, np.float64)       # b, x, y, od, og
    b = fbuf[:nb]
    m = 0
    for a in range(R):
        if not use[a]:
            continue
        b[m] = start[a]; b[m + 1] = finish[a]; m += 2
        t = start[a]
        for j in range(job_off[a], job_off[a + 1]):
            b[m] = js[j]; b[m + 1] = jf[j]; m += 2
            t += job_dur[j]
            b[m] = t; m += 1
    for a in range(R):
        if use_r[a]:
            b[m] = start[a]; b[m + 1] = finish[a]; m += 2
    d = sh_d[r]
    g = sh_g[r]
    st = start[r]
    fi = finish[r]
    x = fbuf[nb:nb + k]
    y = fbuf[nb + k:nb + 2 * k]
    x[0] = 0.0; y[0] = 0.0
    n = 1
    for i in range(m):
        x[n] = d + b[i] - st; y[n] = g; n += 1          # delay: entry -> b
        x[n] = d + b[i] - fi; y[n] = g; n += 1          # delay: exit  -> b
        if can_stretch:
            x[n] = d; y[n] = g + b[i] - fi; n += 1      # stretch: exit -> b
    # sorted set of (x, y) pairs: a stable sort on (x, y) — the order of a
    # stable sort on y followed by a stable sort on x
    ibuf = np.empty(2 * n, np.int64)
    idx = ibuf[:n]
    for i in range(n):
        idx[i] = i
    _msort_xy(idx, ibuf[n:], x, y)
    od = fbuf[nb + 2 * k:nb + 3 * k]
    og = fbuf[nb + 3 * k:nb + 4 * k]
    c = 0
    for i in range(n):
        xi = x[idx[i]]; yi = y[idx[i]]
        if i > 0 and xi == x[idx[i - 1]] and yi == y[idx[i - 1]]:
            continue
        d2 = pyround(xi, 6)
        g2 = pyround(yi, 6)
        if d2 < 0 or g2 < 0 or (d2 == d and g2 == g):
            continue
        od[c] = d2; og[c] = g2; c += 1
    return od[:c], og[:c]


@njit(cache=True)
def proposals_of(r, order, apos, sh_d, sh_g, inst, prm, fronts, n_fronts):
    """``align_proposals`` of r in the decoded state (the shift kicks of
    ``_polish``)."""
    R = inst[0].shape[0]
    J = inst[6].shape[0]
    ws_f, ws_i, ws_b, push, scr = _workspace(R, J, inst[8].shape[0], max_jobs(inst[5]))
    objective(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push, scr)
    return align_proposals(r, apos, sh_d, sh_g, ws_f[0, :R], ws_f[1, :R], ws_f[2, :J],
                           ws_f[3, :J], inst[5], inst[6], fronts, n_fronts, inst[9], inst[10])


@njit(cache=True)
def align_one(r, rel, order, apos, sh_d, sh_g, cur, inst, prm, fronts, n_fronts,
              deadline, cap_b, cap_first, cap_c, steps):
    """``_align`` for one rear r: the first improving shift found by the
    steps selected in the bitmask ``steps`` — (a) one align of r (1), (b) a
    second align of r, the ``cap_b`` nearest to each of the ``cap_first``
    first steps nearest to r's current shift (2), (c) one of the ``cap_c``
    nearest first steps plus one of the 6 nearest aligns of a related rear q
    in ``rel`` (4).  Without (a) the caller vouches that (a) already failed
    on this very state.  Returns (found, d_r, g_r, q, d_q, g_q, obj, n_evals) with
    q = -1 when only r moves; ``sh_d``/``sh_g`` are left unchanged.  Gives up
    (found = 0) once ``deadline`` (perf_counter) passes.

    The proposals are absolute boundary positions, so different first steps
    keep leading to the same second state: every priced state is memoised
    (a state seen before did not improve, or the scan would have returned),
    and the schedule of each first step is decoded once and kept for (b) and
    (c).  Same states visited in the same order as without the memo."""
    E = inst[0]
    job_off = inst[5]
    job_dur = inst[6]
    R = E.shape[0]
    J = job_dur.shape[0]
    ws_f, ws_i, ws_b, push, scr = _workspace(R, J, inst[8].shape[0], max_jobs(inst[5]))
    start = ws_f[0, :R]; finish = ws_f[1, :R]; js = ws_f[2, :J]; jf = ws_f[3, :J]
    d0 = sh_d[r]; g0 = sh_g[r]
    nev = 0
    kbuf = np.empty(1 + 3 * (4 * R + 3 * J), np.float64)  # proposal keys (any r)
    nbuf = np.empty(max(cap_b, 6), np.int64)
    seen1 = Dict.empty(key_type=_K2, value_type=_F8)     # r's shift -> priced
    seen2 = Dict.empty(key_type=_K5, value_type=_F8)     # (r, q shifts) -> priced
    dep = inst[11]
    objective(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b, push, scr)
    D1, G1 = align_proposals(r, apos, sh_d, sh_g, start, finish, js, jf, job_off,
                             job_dur, fronts, n_fronts, inst[9], inst[10])
    base = _base(ws_f, ws_i, R, J, sh_d, sh_g)
    aff_r = _affected(dep, apos[r], -1, scr[17])
    K1 = D1.shape[0]
    # (a) one align of r — or, when the caller already ran (a) on this very
    # state without success, its states are known not to improve
    for k in range(K1):
        seen1[(D1[k], G1[k])] = 1.0
        if not steps & 1:
            continue
        sh_d[r] = D1[k]; sh_g[r] = G1[k]
        o = objective_from(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                           push, scr, base, 0, aff_r, scr[18], cur)
        nev += 1
        if o < cur - 1e-9:
            sh_d[r] = d0; sh_g[r] = g0
            return 1, D1[k], G1[k], -1, 0.0, 0.0, o, nev
    sh_d[r] = d0; sh_g[r] = g0
    if _now() >= deadline:
        return 0, 0.0, 0.0, -1, 0.0, 0.0, cur, nev
    # first steps escalated by (b)/(c): the cap_first nearest to r's current shift
    key1 = np.empty(K1, np.float64)
    for i in range(K1):
        key1[i] = abs(0.0 + D1[i] + G1[i] - (0.0 + d0 + g0))
    near1 = np.argsort(key1, kind="mergesort")
    F = near1[:min(cap_first, K1)].copy()
    F.sort()
    FC = near1[:min(cap_c, K1)].copy()
    FC.sort()
    # (b) a second align of r: the front it targets is re-placed once r moves.
    # The schedule of each first step is kept for (c).
    S1 = np.empty((K1, 2 * R + 2 * J), np.float64)
    have1 = np.zeros(K1, np.bool_)
    for kk in range(F.shape[0] if steps & 2 else 0):
        k = F[kk]
        sh_d[r] = D1[k]; sh_g[r] = G1[k]
        objective_from(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                       push, scr, base, 0, aff_r, scr[18], np.inf)
        nev += 1
        S1[k, :R] = start; S1[k, R:2 * R] = finish
        S1[k, 2 * R:2 * R + J] = js; S1[k, 2 * R + J:] = jf
        have1[k] = True
        D2, G2 = align_proposals(r, apos, sh_d, sh_g, start, finish, js, jf, job_off,
                                 job_dur, fronts, n_fronts, inst[9], inst[10])
        key2 = kbuf[:D2.shape[0]]
        for i in range(D2.shape[0]):
            key2[i] = abs(0.0 + D2[i] + G2[i] - (0.0 + D1[k] + G1[k]))
        N2 = _nearest(key2, min(cap_b, D2.shape[0]), nbuf)
        for i2 in range(N2.shape[0]):
            k2 = N2[i2]
            if (D2[k2], G2[k2]) in seen1:
                continue
            seen1[(D2[k2], G2[k2])] = 1.0
            sh_d[r] = D2[k2]; sh_g[r] = G2[k2]
            o = objective_from(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                               push, scr, base, 0, aff_r, scr[18], cur)
            nev += 1
            if o < cur - 1e-9:
                sh_d[r] = d0; sh_g[r] = g0
                return 1, D2[k2], G2[k2], -1, 0.0, 0.0, o, nev
        if (kk & 7) == 7 and _now() >= deadline:
            sh_d[r] = d0; sh_g[r] = g0
            return 0, 0.0, 0.0, -1, 0.0, 0.0, cur, nev
    sh_d[r] = d0; sh_g[r] = g0
    # (c) a coordinated pair: r's first align + a near align of a related rear
    for kk in range(FC.shape[0] if steps & 4 else 0):
        k = FC[kk]
        sh_d[r] = D1[k]; sh_g[r] = G1[k]
        if not have1[k]:
            objective_from(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i, ws_b,
                           push, scr, base, 0, aff_r, scr[18], np.inf)
            nev += 1
            S1[k, :R] = start; S1[k, R:2 * R] = finish
            S1[k, 2 * R:2 * R + J] = js; S1[k, 2 * R + J:] = jf
            have1[k] = True
        s1 = S1[k, :R]; f1 = S1[k, R:2 * R]
        j1s = S1[k, 2 * R:2 * R + J]; j1f = S1[k, 2 * R + J:]
        for qi in range(rel.shape[0]):
            q = rel[qi]
            dq0 = sh_d[q]; gq0 = sh_g[q]
            d1 = 0.0 + dq0 + gq0
            DQ, GQ = align_proposals(q, apos, sh_d, sh_g, s1, f1, j1s, j1f, job_off,
                                     job_dur, fronts, n_fronts, inst[9], inst[10])
            key = kbuf[:DQ.shape[0]]
            for i in range(DQ.shape[0]):
                key[i] = abs(0.0 + DQ[i] + GQ[i] - d1)
            near = _nearest(key, min(6, DQ.shape[0]), nbuf)
            for i in range(near.shape[0]):
                dq = DQ[near[i]]; gq = GQ[near[i]]
                st = (D1[k], G1[k], float(q), dq, gq)
                if st in seen2:
                    continue
                seen2[st] = 1.0
                sh_d[q] = dq; sh_g[q] = gq
                o = objective_from(True, order, apos, sh_d, sh_g, inst, prm, ws_f, ws_i,
                                   ws_b, push, scr, base, 0, _affected(dep, apos[r], apos[q], scr[17]),
                                   scr[18], cur)
                nev += 1
                sh_d[q] = dq0; sh_g[q] = gq0
                if o < cur - 1e-9:
                    sh_d[r] = d0; sh_g[r] = g0
                    return 1, D1[k], G1[k], q, dq, gq, o, nev
        if (kk & 7) == 7 and _now() >= deadline:
            break
    sh_d[r] = d0; sh_g[r] = g0
    return 0, 0.0, 0.0, -1, 0.0, 0.0, cur, nev
