# Public development fixtures

The first fixture family is defined by the [settled revenue task
card](../task_cards/settled_revenue.md). Generate public tables and their public
task contract using `safety_lab.datasets.generate_sales_fixture`.

The base variant contains order and item tables with one-to-many relationships.
The equal-amount variant adds another order with an amount already present in the
base data. Both variants use the same metric definition and expose their data to
the analyst. No expected answers or private random seeds are stored here.

These small, deterministic cases are public developer regression fixtures.
They are not model evaluation episodes or a held-out benchmark. Keep the private
evaluator and canonical reference events out of future actor and reviewer mounts;
source-tree separation alone is not access control.
