"""Tenant B runner: the same QASPER workload as Tenant A, authenticated as Tenant B's user through ZITADEL (federated_user)."""
from tenant_a_batch import main

if __name__ == "__main__":
    main(default_identity="user")
