from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class SimulationResults:
    temperature: float
    pressure: float
    concentrations: Dict[str, float]
    conversion: float
    residence_time: float
    state: Any  # Cantera state object

@dataclass
class ReactorResults:
    time: float
    concentrations: Dict[str, float]
    state: Any  # Cantera state object

@dataclass
class EconomicResults:
    product_values: Dict[str, float]
    total_value: float
    net_value: float
    weighted_feed_values: Dict[str, float]

@dataclass
class ReactorConfig:
    temperature: float
    pressure: float
    initial_composition: Dict[str, float]
    residence_time: float
    sigma: float
    recycle_ratios: Dict[str, float]
    max_iterations: int
    convergence_tol: float
    mass_balance_tol: float = 1e-6

@dataclass
class RecycleResults:
    reactor_results: ReactorResults
    recycle_streams: List[Dict[str, float]]
    final_feed: Dict[str, float]
    iterations: int
    converged: bool
    gas: Any  
    recycle_to_feed_ratio: float
    initial_moles: float
    final_recycle_moles: float
    mass_balance_history: List[Dict[str, float]]
    recycle_ratios: Dict[str, float]  