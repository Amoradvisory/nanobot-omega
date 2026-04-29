"""Tests anti-regression du filtre 'gratuit' du worker 2ememain.

Lance avec:  python -m pytest workspace/test_filter.py -v
ou simplement: python workspace/test_filter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_veille_2ememain import is_truly_free


def check(label, price_raw, title, expect_ok):
    ok, reason = is_truly_free(price_raw, title)
    status = "PASS" if ok == expect_ok else "FAIL"
    print(f"  [{status}] {label!r}: ok={ok} reason={reason}")
    assert ok == expect_ok, f"{label}: expected {expect_ok}, got {ok} ({reason})"


def test_truly_free():
    check("Gratuit FR exact", "Gratuit", "Canape gris", True)
    check("Gratis NL exact", "Gratis", "Tafel hout", True)
    check("0,00 EUR symbol", "0,00 €", "Lampadaire", True)
    check("0 EUR symbol", "0 €", "Etagere", True)
    check("EUR 0,00 prefix", "€ 0,00", "Bibliotheque", True)


def test_paid_must_be_rejected():
    # CAS PRINCIPAL DU BUG: le filtre buggy acceptait toutes ces lignes.
    check("50 EUR", "50,00 €", "Laptop Lenovo i5 16Go RAM Win 11", False)
    check("150 EUR", "150,00 €", "HP Docking Station G5 NEUF", False)
    check("1.250 EUR", "1.250,00 €", "Velo electrique", False)
    check("5 EUR", "5,00 €", "Livre poche", False)
    check("Prix vide", "", "Truc gratuit", False)  # pas de prix DOM => reject


def test_negative_token_in_title():
    # 'Gratuit' avec un token blacklist => reject (e.g. annonce 'cherche')
    check("cherche", "Gratuit", "Cherche frigo", False)
    check("estimation gratuite", "Gratuit", "Estimation gratuite de votre maison", False)
    check("contre service", "Gratuit", "A donner contre service rendu", False)
    check("frais", "Gratuit", "Frais de livraison a votre charge", False)


def test_edge_cases():
    check("None price", None, "Titre", False)
    check("Whitespace price", "   ", "Titre", False)
    check("'A donner' (sans prix)", "A donner", "Canape", False)  # reject par defaut


if __name__ == "__main__":
    print("=== test_truly_free ===")
    test_truly_free()
    print("=== test_paid_must_be_rejected ===")
    test_paid_must_be_rejected()
    print("=== test_negative_token_in_title ===")
    test_negative_token_in_title()
    print("=== test_edge_cases ===")
    test_edge_cases()
    print("\nALL TESTS PASSED.")
