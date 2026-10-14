"""Generate a deliberately messy fake tuition-centre dataset (no real people)."""
from __future__ import annotations
import random
import pandas as pd
from .detectors import valid_nric

_ST = "JZIHGFEDCBA"; _W = (2, 7, 6, 5, 4, 3, 2)


def make_nric(rng: random.Random, prefix: str = "S") -> str:
    digits = [rng.randint(0, 9) for _ in range(7)]
    total = sum(d * w for d, w in zip(digits, _W)) + (4 if prefix == "T" else 0)
    return f"{prefix}{''.join(map(str, digits))}{_ST[total % 11]}"


def messy_students(n: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    first = ["Wei Ming", "Siti", "Priya", "Jun Hao", "Aisha", "Daniel", "Mei Ling", "Ravi", "Hui Min", "Farid"]
    last = ["Tan", "Lim", "Nair", "Rahman", "Ong", "Chua", "Singh", "Lee"]
    rows = []
    for i in range(n):
        nric = make_nric(rng, rng.choice("ST"))
        if rng.random() < 0.06:
            nric = nric[:-1] + ("Z" if nric[-1] != "Z" else "A")          # bad checksum
        ph = f"{rng.choice('689')}{rng.randint(1000000, 9999999)}"
        ph = rng.choice([ph, f"+65 {ph[:4]} {ph[4:]}", f"65{ph}", ph])
        name = f"{rng.choice(first)} {rng.choice(last)}"
        email = f"{name.lower().replace(' ', '.')}{rng.randint(1, 99)}@example.com"
        if rng.random() < 0.05:
            email = email.replace("@", "")
        rows.append({
            "student_name": name if rng.random() > 0.03 else None,
            "nric": nric.lower() if rng.random() < 0.1 else nric,
            "phone": ph,
            "email": email.upper() if rng.random() < 0.08 else email,
            "postal_code": f"{rng.randint(100000, 829999)}",
            "date_joined": f"20{rng.randint(19, 25)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "parent_consent": rng.choice(["yes", "yes", "unknown", None]),
            "country": rng.choice(["SG"] * 8 + ["Malaysia", "India"]),
        })
    df = pd.DataFrame(rows)
    dups = df.sample(8, random_state=seed)
    df = pd.concat([df, dups], ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)
    df["student_name"] = df["student_name"].map(lambda x: f" {x} " if isinstance(x, str) and rng.random() < 0.1 else x)
    return df


# --------------------------------------------------------------------------
# Accounting-firm demo (all fake)
# --------------------------------------------------------------------------
ANCHOR = pd.Timestamp("2026-10-01")   # fixed so demos and tests are reproducible


def messy_clients(n: int = 60, seed: int = 11) -> pd.DataFrame:
    """Client list with CDD fields. Deliberately incomplete: blank beneficial owners, stale reviews..."""
    rng = random.Random(seed)
    sectors = ["Trading", "F&B", "Logistics", "Consulting", "Holdings", "Tech", "Clinic"]
    owners = ["Tan Wei Ming", "Siti Rahman", "Priya Nair", "Lim Jun Hao", "Chua Mei Ling", "Ravi Singh", "Ong Hui Min"]
    rows = []
    for i in range(1, n + 1):
        uen = f"20{rng.randint(10, 24)}{rng.randint(10000, 99999)}{rng.choice('ABCDEFGHK')}"
        last = ANCHOR - pd.Timedelta(days=rng.randint(10, 900))
        rows.append({
            "client_id": f"C{i:03d}",
            "client_name": f"{rng.choice(sectors)} {rng.choice(['Pte Ltd', 'LLP', 'Pte. Ltd.'])} {i}",
            "uen": uen,
            "director_nric": make_nric(rng, rng.choice("ST")),
            "contact_email": f"owner{i}@example.com",
            "beneficial_owner": rng.choice(owners) if rng.random() > 0.25 else None,
            "risk_rating": rng.choice(["low", "low", "medium", "high"]) if rng.random() > 0.3 else None,
            "pep_screening": rng.choice(["clear", "clear", "clear", "pending"]) if rng.random() > 0.35 else None,
            "source_of_funds": rng.choice(["trading profits", "shareholder loan", "retained earnings"]) if rng.random() > 0.45 else None,
            "last_cdd_date": last.strftime("%Y-%m-%d") if rng.random() > 0.1 else None,
            "date_onboarded": (ANCHOR - pd.Timedelta(days=rng.randint(200, 2400))).strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


def messy_payroll(clients: int = 12, per_client: int = 6, seed: int = 5) -> pd.DataFrame:
    rng = random.Random(seed)
    first = ["Wei Ming", "Siti", "Priya", "Jun Hao", "Aisha", "Daniel", "Mei Ling", "Ravi"]
    last = ["Tan", "Lim", "Nair", "Rahman", "Ong", "Chua", "Singh", "Lee"]
    rows = []
    for c in range(1, clients + 1):
        for _ in range(per_client):
            sal = rng.randint(2200, 9800)
            rows.append({
                "client_id": f"C{c:03d}",
                "employee_name": f"{rng.choice(first)} {rng.choice(last)}",
                "nric": make_nric(rng, rng.choice("ST")),
                "basic_salary": str(sal),
                "cpf_employee": str(round(sal * 0.2)),
                "bank_account": f"{rng.randint(10**9, 10**10 - 1)}",
                "date_joined": (ANCHOR - pd.Timedelta(days=rng.randint(30, 2000))).strftime("%Y-%m-%d"),
            })
    return pd.DataFrame(rows)


def assignments() -> pd.DataFrame:
    """Which staff are assigned to which clients (drives client-segregation row filters)."""
    rows = []
    for i in range(1, 13):
        cid = f"C{i:03d}"
        rows.append({"staff": "sam", "client_id": cid}) if i <= 6 else rows.append({"staff": "jo", "client_id": cid})
        if i in (1, 2, 7):
            rows.append({"staff": "ivy", "client_id": cid})
    return pd.DataFrame(rows)


SAMPLES = {
    "Tuition centre: students": messy_students,
    "Accounting firm: client CDD list": messy_clients,
    "Accounting firm: client payroll": messy_payroll,
}
