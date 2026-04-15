'''
# milp_pyomo.py
Returns a Pyomo model for the problem

# milp_solver.py
Contains all funcions for solving the problem, using milp_pyomo.py
* Methods for
    * prepare_pyomo_data Coverting raw data into pyomo data
    * configure_solver (depending on which one you are using)
    * solve to call the solver with the deired configuration
    * get_solution Getting the solution from pyomo
* ... 

# aircraft_poisitioning.py
Define a class, named Application, with the following features:

* Atributes:
    * instance: input data corresponding to the particular case of the 
    * solution: ouput data obtained after solving (initially empty, and filled when solved)
* Methods for the following purposes
    * read raw data (calls code from instance_io.py)
    * solver (a reference to .py script, which contains a solver class in \solvers )
    * configure_solver (calls de configure solver of the above class)
    * solve (calls the solve in the above class)
    * get solution (calls the get solution in the above class)
    * check solution (calls the script check solution)
    * plot solution (calls the script in plot_schedule)

The objective is to define here everything that is common to no matter what solving method we are using and calling whatever is specific acording to the selected solver
'''
 