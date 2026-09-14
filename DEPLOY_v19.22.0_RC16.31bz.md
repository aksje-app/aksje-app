# Deploy RC16.31bz

1. Deploy the clean DELTA files to the same GitHub/Render branch used by web, scheduler and paper scanner.
2. Confirm all services report `v19.22.0-rc16.31bz` and the same commit.
3. Start one manual Utkast - Norge run.
4. Observe the same execution from 0-100% without manual refresh.
5. Specifically confirm that the long interval between initial market-data work and evidence/baseline work now advances through intermediate percentages instead of remaining flat and then jumping about 30 points.
6. Confirm the percentage never decreases for the same execution ID.
7. Confirm the run still reaches REPORT/COMPLETE and creates the same report artifacts.

No environment-variable changes are required.
