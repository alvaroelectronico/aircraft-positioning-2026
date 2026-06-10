Option 1: creating a dummy constructive_heuristic.py within solvers to iteratively improve it.

Option 2: creating the structure first as follows:

* constructive_heuristic.py
Constructive algorithm where several functions are called:
    do until max_run time:
        do until there are aircrafts to asign:
            * select an airplane
            * select a position
            * insert aircraft into postion
        explore a local search withe aicraft reinserions or swaps




\constructive_heuristic (or a different and better name): 
functions to be called by the constructive algorithm:
* sort_airplanes: sort planes according to some criterion/criteria to 
* sort_positions: sort positions 
* random_biased_selection: given a sorted list with elements to pick from, select on item where the probabilities for the items follow a geometric progression (the more attractive the item the more likely to chose)
* insert_airplane_to_position
* re-insertions
* swaps