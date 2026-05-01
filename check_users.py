
from user_store import init_user_store, list_users, using_postgres, user_count

print("using_postgres:", using_postgres())
print("init_user_store:", init_user_store())
print("user_count:", user_count())
print("users:", list_users())
