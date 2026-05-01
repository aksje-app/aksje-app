
import os
from paper_store import using_postgres, init_db
from trading_settings import save_rules, load_rules, DEFAULT_RULES

print("DATABASE_URL present:", bool(os.getenv("DATABASE_URL")))
print("using_postgres:", using_postgres())
print("init_db:", init_db())
print("save trading rules:", save_rules(DEFAULT_RULES))
print("load trading rules keys:", sorted(load_rules().keys()))
