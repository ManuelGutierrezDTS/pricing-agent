# main.py
"""
Pricing Agent - Main Entry Point
Sistema completo de análisis y validación de precios
"""

import sys
import json
from datetime import datetime

from config import SINGLE_ANALYSIS, PATH_CONFIG
from modules.data.unity_catalog import check_and_refresh_unity
from modules.analysis.integrated import run_integrated_analysis


def print_header():
    """Print application header"""
    print("="*70)
    print("💰 ADVANCED PRICING AGENT v3.0")
    print("="*70)
    print("Features: Multi-Equipment | Multistop | Hotshot | ZIP Resolution | Case-Insensitive")
    print("="*70)


def print_executive_summary(results: dict):
    """Print executive summary"""
    print("\n" + "="*70)
    print("📋 EXECUTIVE SUMMARY")
    print("="*70)
    
    final_rating = results["final_rating"]
    combined_confidence = results["combined_confidence"]
    proposed_margin_pct = results['prc_validation']['proposed_margin_pct']
    
    # LÓGICA CORREGIDA: NO aprobar si no hay datos o baja confianza
    if final_rating == "NO_DATA":
        print(f"\n⚠️ DECISION: NEEDS MANUAL REVIEW")
        print(f"   ⚠️ Reason: No historical data available")
        print(f"   📊 Confidence too low ({combined_confidence}%) to auto-approve")
    elif combined_confidence < 30:
        print(f"\n⚠️ DECISION: NEEDS MANUAL REVIEW")
        print(f"   ⚠️ Reason: Confidence too low ({combined_confidence}%)")
    elif final_rating in ["EXCELLENT", "GOOD"]:
        print(f"\n✅ DECISION: APPROVE PRICE")
    elif final_rating in ["ACCEPTABLE"]:
        if combined_confidence >= 60:
            print(f"\n⚠️ DECISION: REVIEW PRICE (Acceptable with good confidence)")
        else:
            print(f"\n⚠️ DECISION: NEEDS MANUAL REVIEW (Low confidence)")
    else:
        print(f"\n❌ DECISION: REJECT/RENEGOTIATE PRICE")
    
    print(f"\nDetails:")
    print(f"   Rating: {final_rating}")
    print(f"   Confidence: {combined_confidence}%")
    print(f"   Load Type: {results['load_type']}")
    print(f"   Proposed Margin: {proposed_margin_pct:.1f}%")
    
    if results.get("margin_flag") == "below_minimum":
        print(f"   🚨 WARNING: Margin below minimum threshold")
    
    # 🆕 NEGOTIATION RANGE MEJORADO
    negotiation = results.get("negotiation_range", {})
    if negotiation.get("target_rate") and negotiation.get("max_buy"):
        target = negotiation['target_rate']
        carrier_cost = negotiation['carrier_cost']
        max_buy = negotiation['max_buy']
        spread = max_buy - target
        
        print(f"\n💡 NEGOTIATION RANGE:")
        print(f"   ┌─────────────────────────────────────┐")
        print(f"   │ Target Rate (minimum):   ${target:>10,.2f} │")
        print(f"   │ Carrier Cost (midpoint): ${carrier_cost:>10,.2f} │ ← Your cost")
        print(f"   │ Max Buy (maximum):       ${max_buy:>10,.2f} │")
        print(f"   └─────────────────────────────────────┘")
        print(f"   Range spread: ${spread:,.2f}")
    
    # Acción recomendada
    proposed_price = results['inputs']['proposed_price']
    suggested_price = results.get('suggested_price', proposed_price)
    diff = suggested_price - proposed_price
    
    # Solo dar recomendación si hay confianza suficiente
    if combined_confidence >= 30 and abs(diff) > 100:
        print(f"\n💡 RECOMMENDED ACTION:")
        if diff > 0:
            print(f"   Increase price to ${suggested_price:,.2f} (+${diff:.2f})")
        else:
            print(f"   Reduce price to ${suggested_price:,.2f} (${diff:.2f})")
    elif combined_confidence >= 30 and abs(diff) <= 100:
        print(f"\n✅ Price appears reasonable based on available data")
    else:
        print(f"\n⚠️ Insufficient data for reliable pricing recommendation")
        print(f"   Suggested actions:")
        print(f"   • Verify similar historical loads exist")
        print(f"   • Check if lane/customer combination is new")
        print(f"   • Consider manual price review")


def save_results(results: dict, output_file: str):
    """Save results to JSON file"""
    try:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=4, default=str)
        print(f"\n💾 Results saved to: {output_file}")
        return True
    except Exception as e:
        print(f"\n❌ Error saving results: {e}")
        return False


def main():
    """Main function"""
    
    try:
        # Print header
        print_header()
        
        # Check and load Unity Catalog
        print("\n🔄 Checking Unity Catalog...")
        try:
            unity_df = check_and_refresh_unity()
        except Exception as e:
            print(f"❌ Fatal error loading Unity Catalog: {e}")
            return 1
        
        # Run integrated analysis
        print(f"\n📊 Running analysis...")
        
        try:
            results = run_integrated_analysis(unity_df, SINGLE_ANALYSIS)
            
            if "error" in results:
                print(f"\n❌ Error: {results['error']}")
                return 1
            
            # Save results
            output_file = PATH_CONFIG["results_output"]
            save_results(results, output_file)
            
            # Print executive summary
            print_executive_summary(results)
            
        except Exception as e:
            print(f"\n❌ Error during analysis: {e}")
            import traceback
            traceback.print_exc()
            return 1
        
        print("\n" + "="*70)
        print("✅ ANALYSIS COMPLETED")
        print("="*70)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())