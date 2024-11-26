import numpy as np
from dataclasses import dataclass
from typing import Dict, Any
from constants import Constants
from models import EconomicResults, ReactorResults

@dataclass
class EconomicResults:
    product_values: Dict[str, float]
    total_value: float
    net_value: float
    weighted_feed_values: Dict[str, float]

class MarketPrices:
    """
    Class to handle dynamic market prices.
    """
    def __init__(self):
        # Initialize base market prices excluding C2H2
        self.prices = {
            'CH4': 650,    # Natural gas
            'H2': 4000,    # Hydrogen
            'C2H6': 300,   # Ethane
            'C2H4': 850,   # Ethylene
            'C2H2': 0,     # Acetelene
            'C3H6': 750,   # Propylene
            'C3H8': 650,   # Propane
            'C3H4-P': 750, # Propyne
            'C3H4-A': 750, # Allene
            'C4H6': 750,   # 1,3-Butadiene
            'C4H4': 750,   # Vinylacetylene
            'C4H2': 750,   # Diacetylene
            'C6H6': 1050,  # Benzene
            'NAPH': 0,     # Naphthalene
            'IND': 0       # Indene
        }
        # Dynamically calculate C2H2 price based on C2H2 + H2 → C2H4
        price_c2h4_mol = (self.prices.get('C2H4', 0) / 1000) * (28.054 / 1000)
        price_h2_mol = (self.prices.get('H2', 0) / 1000) * (2.016 / 1000)
        self.prices['C2H2'] = ((price_c2h4_mol - price_h2_mol) / (26.038 / 1000)) * 1000 * 0.5

    def get_price(self, species):
        """
        Get the market price for a given species.
        """
        return self.prices.get(species, 0)

class EconomicAnalysis:
    def __init__(self, gas):
        """
        Initialize economic analysis

        Args:
            gas (cantera.Solution): Cantera gas object containing species data
        """
        self.gas = gas
        self.market_prices = MarketPrices()

    def calculate_economic_value(
        self, 
        reactor_results: ReactorResults,
        fresh_feed_composition: Dict[str, float],
        recycle_ratios: Dict[str, float],
        basis_mass: float = Constants.BASIS_MASS
    ) -> EconomicResults:
        """Calculate economic value of products per ton of mixed feed"""
        # Get all unique species from both feed and products
        all_species = set(fresh_feed_composition.keys()) | set(reactor_results.concentrations.keys())
        
        # Initialize concentrations dict with zeros for all species
        final_concentrations = {sp: reactor_results.concentrations.get(sp, 0.0) for sp in all_species}
        
        # Adjust concentrations for recycled species
        adjusted_concentrations = {}
        total_conc = sum(final_concentrations.values())
        
        for sp, conc in final_concentrations.items():
            # Use the passed recycle_ratios instead of accessing from reactor_results
            recycle_ratio = recycle_ratios.get(sp, 0.0)
            adjusted_conc = conc * (1 - recycle_ratio)
            if adjusted_conc > 0:
                adjusted_concentrations[sp] = adjusted_conc
        
        # Normalize adjusted concentrations
        total_adj_conc = sum(adjusted_concentrations.values())
        normalized_concentrations = {
            sp: conc/total_adj_conc 
            for sp, conc in adjusted_concentrations.items()
        }
        
        # Rest of the calculations remain the same but use normalized_concentrations
        total_molecular_weight = sum(
            conc * self.gas.molecular_weights[self.gas.species_index(sp)]
            for sp, conc in normalized_concentrations.items()
        )
        
        mass_flows = {
            sp: (conc * self.gas.molecular_weights[self.gas.species_index(sp)] * basis_mass) / total_molecular_weight
            for sp, conc in normalized_concentrations.items()
        }
        
        # Calculate product values only for non-recycled products
        product_values = {}
        total_value = 0
        
        for sp in adjusted_concentrations.keys():
            if sp not in fresh_feed_composition:  # Only calculate values for products
                value = mass_flows[sp] * self.market_prices.get_price(sp) / 1000
                product_values[sp] = value
                total_value += value
            else:
                product_values[sp] = 0.0
        
        # Calculate feed cost using fresh feed composition
        feed_mol_weight = sum(
            frac * self.gas.molecular_weights[self.gas.species_index(sp)]
            for sp, frac in fresh_feed_composition.items()
        )
        
        feed_cost = sum(
            basis_mass * (frac * self.gas.molecular_weights[self.gas.species_index(sp)] / feed_mol_weight) * 
            self.market_prices.get_price(sp) / 1000
            for sp, frac in fresh_feed_composition.items()
        )
        
        net_value = total_value - feed_cost
        
        # Calculate weighted feed values using fresh feed composition
        weighted_feed_values = {}
        for sp in final_concentrations.keys():
            if sp in fresh_feed_composition:
                feed_mass = basis_mass * (fresh_feed_composition[sp] * self.gas.molecular_weights[self.gas.species_index(sp)] / feed_mol_weight)
                weighted_feed_values[sp] = feed_mass * self.market_prices.get_price(sp) / 1000
            else:
                weighted_feed_values[sp] = 0.0
                
        return EconomicResults(
            product_values=product_values,
            total_value=total_value,
            net_value=net_value,
            weighted_feed_values=weighted_feed_values
        )