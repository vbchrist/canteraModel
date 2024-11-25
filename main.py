import yaml
import logging
from typing import Dict, Any
from constants import Constants
from output_formatter import OutputFormatter
from economic_analysis import EconomicAnalysis
from reactor_model import ReactorModel, RecycleReactor
from models import ReactorConfig, EconomicResults, RecycleResults

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config(filename: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    try:
        with open(filename, 'r') as file:
            config = yaml.safe_load(file)
            if not config:
                raise ValueError("Empty configuration file")
            return config
    except (FileNotFoundError, yaml.YAMLError) as e:
        logger.error(f"Error loading configuration: {e}")
        raise

def main() -> None:
    logger.info("Starting simulation")
    
    # Load and validate configuration
    config = load_config('config.yaml')
    
    # Create reactor configuration
    reactor_config = ReactorConfig(
        temperature=config['temperature_C'] + Constants.KELVIN_OFFSET,
        pressure=config['pressure'],
        initial_composition=config['initial_composition'],
        residence_time=config['time_total'],
        sigma=config['sigma'],
        recycle_ratios=config['recycle_ratios'],
        max_iterations=config['max_iterations'],
        convergence_tol=config['convergence_tol']
    )
    
    # Create reactor model and run simulation
    base_model = ReactorModel(mechanism=config['mechanism'])
    model = RecycleReactor(base_model)
    
    recycle_results: RecycleResults = model.simulate_with_recycle(reactor_config)
    
    # Calculate economics
    econ = EconomicAnalysis(gas=base_model.gas)
    economic_results: EconomicResults = econ.calculate_economic_value(
        reactor_results=recycle_results.reactor_results,
        initial_composition=reactor_config.initial_composition,
        recycle_ratios=reactor_config.recycle_ratios
    )

    # Format output
    formatter = OutputFormatter(sigma=config['sigma'])
    formatter.print_simulation_parameters(reactor_config)
    formatter.print_recycle_info(recycle_results)
    formatter.print_economic_results(recycle_results, econ, economic_results)

if __name__ == "__main__":
    main()
