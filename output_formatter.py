import numpy as np
from constants import Constants
from economic_analysis import EconomicAnalysis
from reactor_model import RecycleResults
from models import ReactorConfig, RecycleResults, EconomicResults

class OutputFormatter:
    def __init__(self, sigma: float):
        self.sigma = sigma

    def print_simulation_parameters(self, config: ReactorConfig) -> None:
        print(f"\nRunning PFR simulation with recycle:")
        print(f"Temperature: {config.temperature - Constants.KELVIN_OFFSET}°C")
        print(f"Pressure: {config.pressure/Constants.PRESSURE_ATM:.1f} atm")
        print(f"Residence time: {config.residence_time} s")
        print("\nRecycle ratios:")
        for species, ratio in config.recycle_ratios.items():
            print(f"{species}: {ratio*100:.1f}%")

    def print_recycle_info(self, recycle_results: RecycleResults) -> None:
        print(f"\nRecycle convergence:")
        print(f"Iterations required: {recycle_results.iterations}")
        print(f"Converged: {recycle_results.converged}")
        print("\nFinal feed composition after recycling:")
        for species, conc in recycle_results.final_feed.items():
            print(f"{species}: {conc*100:.2f}%")

    def print_economic_results(
            self, 
            recycle_results: RecycleResults, 
            econ: 'EconomicAnalysis', 
            economic_results: EconomicResults,
            fresh_feed_composition: dict
        ) -> None:
        product_values = economic_results.product_values
        total_value = economic_results.total_value
        net_value = economic_results.net_value
        weighted_feed_values = economic_results.weighted_feed_values
        
        print("\nFinal concentrations and values of target species:")
        print("-" * 115)
        headers = ["Species", "Price", "In Conc.", "In Mass", "Out Conc.", "Out Mass", "Feed Value", "Product Value"]
        units = ["", "($/ton)", "(mol%)", "(mass%)", "(mol%)", "(mass%)", "($/ton feed)", "($/ton feed)"]
        print(f"{headers[0]:<8} {headers[1]:>10} {headers[2]:>10} {headers[3]:>10} {headers[4]:>10} {headers[5]:>10} {headers[6]:>12} {headers[7]:>12}")
        print(f"{'':8} {units[1]:>10} {units[2]:>10} {units[3]:>10} {units[4]:>10} {units[5]:>10} {units[6]:>12} {units[7]:>12}")
        print("-" * 115)
        
        gas = recycle_results.reactor_results.state
        molecular_weights = {
            sp: gas.molecular_weights[gas.species_index(sp)] 
            for sp in set(list(recycle_results.reactor_results.concentrations.keys()) + 
                         list(fresh_feed_composition.keys()))
        }
        
        # Get concentrations from reactor outlet
        reactor_concentrations = recycle_results.reactor_results.concentrations
        
        # Calculate initial mass percentages using fresh feed
        initial_total_mass = sum(conc * molecular_weights[sp] 
                         for sp, conc in fresh_feed_composition.items())
        
        # Rest of the adjustments for outlet concentrations...
        adjusted_concentrations = {}
        total_conc = sum(reactor_concentrations.values())
        
        for sp, conc in reactor_concentrations.items():
            recycle_ratio = recycle_results.recycle_ratios.get(sp, 0.0)
            adjusted_conc = conc * (1 - recycle_ratio)
            if adjusted_conc > 0:
                adjusted_concentrations[sp] = adjusted_conc
        
        # Normalize adjusted concentrations
        total_adj_conc = sum(adjusted_concentrations.values())
        normalized_concentrations = {
            sp: conc/total_adj_conc 
            for sp, conc in adjusted_concentrations.items()
        }
        
        # Calculate mass percentages based on adjusted concentrations
        total_mass = sum(conc * molecular_weights[sp] 
                        for sp, conc in normalized_concentrations.items())
        
        total_mass_perc = 0.0
        total_conc = 0.0
        
        for species in reactor_concentrations.keys():
            conc = normalized_concentrations.get(species, 0.0)
            in_conc = fresh_feed_composition.get(species, 0.0)  # Use fresh feed instead of final_feed
            in_mass_perc = (in_conc * molecular_weights[species] / initial_total_mass) * 100 if in_conc > 0 else 0.0
            out_mass_perc = (conc * molecular_weights[species] / total_mass) * 100 if conc > 0 else 0.0
            value = product_values.get(species, 0.0)
            feed_value = weighted_feed_values.get(species, 0.0)
            market_price = econ.market_prices.get_price(species)
            
            if conc > self.sigma:
                print(f"{species:<8} {market_price:>10.2f} {in_conc*100:>10.2f} {in_mass_perc:>10.2f} "
                      f"{conc*100:>10.2f} {out_mass_perc:>10.2f} {feed_value:>12.2f} {value:>12.2f}")
                total_conc += conc*100
                total_mass_perc += out_mass_perc
            else:
                print(f"{species:<8} {market_price:>10.2f} {in_conc*100:>10.2f} {in_mass_perc:>10.2f} "
                      f"{'< σ':>10} {'< σ':>10} {feed_value:>12.2f} {value:>12.2f}")
        
        print("-" * 115)
        total_feed_value = sum(weighted_feed_values.values())
        print(f"{'Total':<8} {'-':>10} {total_conc:>10.2f} {total_mass_perc:>10.2f} {total_feed_value:>12.2f} {total_value:>12.2f}")
        print("-" * 115)
        print(f"{'Net Value':<52} {net_value:>12.2f} {'USD/ton feed':<12}")
        print(f"{'Recycle/Feed Ratio':<52} {recycle_results.recycle_to_feed_ratio:>12.2f} {'ton/ton':<12}")
        print("-" * 115)
   