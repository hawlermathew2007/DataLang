wget https://software.yugabyte.com/releases/2026.1.2.0/yugabyte-2026.1.2.0-b137-linux-x86_64.tar.gz
echo "$(curl -L https://software.yugabyte.com/releases/2026.1.2.0/yugabyte-2026.1.2.0-b137-linux-x86_64-tar.gz.sha) *yugabyte-2026.1.2.0-b137-linux-x86_64.tar.gz" | shasum --check
tar xvfz yugabyte-2026.1.2.0-b137-linux-x86_64.tar.gz && cd yugabyte-2026.1.2.0/

echo "See tests/test_yugabytedb.py to get a view of how to work with the DB with Python. Other options: use connect_yugabytedb."
echo "Create the local cluster first then connect."
