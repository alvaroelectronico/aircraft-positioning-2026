# iter_0052_persisted_overrides — carry start_overrides across LNS iters

Same score +0.0191.  LS re-discovers productive overrides quickly each
call, so persisting doesn't help fast_eval.

The change IS structurally cleaner (less rediscovery work) and may help
on instances outside fast_eval.  Per strict protocol: **rejected**.
