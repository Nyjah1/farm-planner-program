#!/usr/bin/env python3
"""
Testa skripts EC agridata cenu ielādei.

Izvada cenas tabulā ar kolonnām: kultūra, price_eur_t, as_of, source.
"""
import sys
from pathlib import Path

# Pievieno projekta sakni Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.market_prices import get_latest_prices_for_catalog


def main():
    """Galvenā funkcija."""
    print("Ielādē cenas no EC Agri-food Data Portal...")
    print("-" * 60)
    
    # Izsauc funkciju ar testa kultūrām
    crop_names = ["Kvieši", "Mieži", "Auzas"]
    prices = get_latest_prices_for_catalog(crop_names)
    
    if not prices:
        print("Nav atrastu cenu datu.")
        print("Iespējamie iemesli:")
        print("  - API nav pieejams")
        print("  - Nav atrastu atbilstošu produktu kodu")
        print("  - Nav cenu datu pēdējās 90 dienās")
        return
    
    # Sagatavo tabulu
    print(f"\n{'Kultūra':<15} {'Cena (EUR/t)':<15} {'Datums':<12} {'Avots':<20}")
    print("-" * 60)
    
    for crop_name in crop_names:
        if crop_name in prices:
            price_info = prices[crop_name]
            price = price_info.get('price_eur_t', 0.0)
            as_of = price_info.get('as_of', 'N/A')
            source = price_info.get('source', 'N/A')
            
            print(f"{crop_name:<15} {price:<15.2f} {as_of:<12} {source:<20}")
        else:
            print(f"{crop_name:<15} {'Nav datu':<15} {'N/A':<12} {'N/A':<20}")
    
    print("-" * 60)
    print(f"Kopā atrastas cenas: {len(prices)}/{len(crop_names)}")


if __name__ == "__main__":
    main()

