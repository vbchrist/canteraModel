import cantera as ct
import numpy as np
from tqdm import tqdm
from models import ReactorConfig, ReactorResults, RecycleResults
import warnings

class ReactorModel:
    def __init__(self, mechanism='aramco.yaml'):
        self.gas = ct.Solution(mechanism)

    def simulate(self, config: ReactorConfig) -> ReactorResults:
        """Run a PFR simulation with given parameters using Lagrangian particle approach."""
        reactor = self._initialize_reactor(config)
        sim = ct.ReactorNet([reactor])
        self._run_simulation(sim, config.residence_time)
        return ReactorResults(
            time=config.residence_time,
            concentrations=self._get_significant_species(reactor, config.sigma),
            state=reactor.thermo
        )

    def _initialize_reactor(self, config: ReactorConfig) -> ct.IdealGasConstPressureReactor:
        """Initialize reactor with given configuration."""
        self.gas.TPX = config.temperature, config.pressure, config.initial_composition
        desired_mass = 1.0  # kg
        required_volume = desired_mass / self.gas.density  # m³
        reactor = ct.IdealGasConstPressureReactor(self.gas)
        reactor.volume = required_volume
        return reactor

    def _run_simulation(self, sim: ct.ReactorNet, residence_time: float) -> None:
        """Run the reactor simulation for given time points."""
        time_points = np.linspace(0, residence_time, 100)
        for t in tqdm(time_points, desc="Reactor simulation", unit="s"):
            sim.advance(t)

    def _get_significant_species(self, reactor: ct.IdealGasConstPressureReactor, sigma: float) -> dict:
        """Filter and return species above concentration threshold."""
        return {
            species: conc for species, conc in zip(self.gas.species_names, reactor.thermo.concentrations)
            if conc > sigma
        }


class RecycleReactor:
    def __init__(self, base_reactor=None):
        self.reactor = base_reactor if base_reactor else ReactorModel()

    def simulate_with_recycle(self, config: ReactorConfig) -> RecycleResults:
        """Simulate reactor with recycle streams until convergence."""
        initial_state = self._initialize_simulation(config)
        previous_compositions = {}
        recycle_streams = []
        mass_balance_history = []
        best_error = float('inf')
        stagnation_counter = 0
        
        for iteration in range(config.max_iterations):
            result = self.reactor.simulate(config)
            recycle_stream = self._calculate_recycle_stream(result, config, initial_state)
            recycle_streams.append(recycle_stream)
            
            mass_balance = self._verify_mass_balance(
                initial_state, 
                ct.Quantity(result.state), 
                recycle_stream, 
                config
            )
            mass_balance_history.append(mass_balance)
            
            current_error = mass_balance['relative_error']
            if current_error < best_error:
                best_error = current_error
                stagnation_counter = 0
            else:
                stagnation_counter += 1
                
            if stagnation_counter >= 3:
                warnings.warn("Terminating early due to stagnation in solution")
                break
                
            if not mass_balance['is_balanced']:
                warnings.warn(
                    f"Mass balance error at iteration {iteration}. "
                    f"Relative Error: {mass_balance['relative_error']:.2%}"
                )
            
            new_feed = self._calculate_new_feed(config, initial_state, recycle_stream)
            
            if self._check_convergence(new_feed, previous_compositions, config):
                break
                
            # Apply damping
            for species in new_feed:
                if species in previous_compositions:
                    new_feed[species] = 0.7 * new_feed[species] + 0.3 * previous_compositions[species]
                    
            previous_compositions = new_feed.copy()
            config.initial_composition = new_feed

        return self._create_recycle_results(
            result=result,
            recycle_streams=recycle_streams,
            config=config,
            iteration=iteration,
            initial_state=initial_state,
            final_recycle=recycle_stream,
            mass_balance_history=mass_balance_history  # Add to results
        )

    def _initialize_simulation(self, config: ReactorConfig) -> ct.Quantity:
        """Initialize simulation and return initial state."""
        self.reactor.gas.TPX = config.temperature, config.pressure, config.initial_composition
        return ct.Quantity(self.reactor.gas)

    def _calculate_recycle_stream(self, result: ReactorResults, config: ReactorConfig, 
                                initial_state: ct.Quantity) -> dict:
        """Calculate recycle stream compositions."""
        final_quantity = ct.Quantity(result.state)
        
        reactor_mass = initial_state.mass
        if hasattr(self, '_previous_recycle'):
            reactor_mass += sum(
                moles * self.reactor.gas.molecular_weights[self.reactor.gas.species_index(species)]
                for species, moles in self._previous_recycle.items()
            )
        
        recycle_stream = {}
        total_outlet_mass = 0
        total_recycled_mass = 0
        
        for i, species in enumerate(result.state.species_names):
            species_mass = reactor_mass * result.state.X[i]
            species_moles = species_mass / self.reactor.gas.molecular_weights[i]
            ratio = config.recycle_ratios.get(species, 0.0)
            
            total_outlet_mass += species_mass
            if ratio > 0:
                recycle_stream[species] = species_moles * ratio
                recycled_mass = species_mass * ratio
                total_recycled_mass += recycled_mass
        
        self._previous_recycle = recycle_stream.copy()
        
        return recycle_stream

    def _calculate_new_feed(self, config: ReactorConfig, initial_state: ct.Quantity, 
                          recycle_stream: dict) -> dict:
        """Calculate new feed composition from fresh feed and recycle stream."""
        new_feed = {
            species: config.initial_composition[species] * initial_state.moles
            for species in config.initial_composition
        }
        
        for species, recycled_moles in recycle_stream.items():
            new_feed[species] = new_feed.get(species, 0) + recycled_moles
            
        total_moles = sum(new_feed.values())
        return {species: moles/total_moles for species, moles in new_feed.items()}

    @staticmethod
    def _check_convergence(new_feed: dict, previous_compositions: dict, 
                          config: ReactorConfig) -> bool:
        """Check if recycle stream has converged."""
        if not previous_compositions:
            return False
            
        return all(
            abs(new_feed.get(species, 0) - previous_compositions.get(species, 0)) 
            <= config.convergence_tol
            for species in config.recycle_ratios
        )

    def _create_recycle_results(self, result: ReactorResults, recycle_streams: list,
                              config: ReactorConfig, iteration: int, 
                              initial_state: ct.Quantity,
                              final_recycle: dict,
                              mass_balance_history: list) -> RecycleResults:
        """Create final results object."""
        final_recycle_moles = sum(final_recycle.values())
        return RecycleResults(
            reactor_results=result,
            recycle_streams=recycle_streams,
            final_feed=config.initial_composition,
            iterations=iteration + 1,
            converged=iteration < config.max_iterations - 1,
            gas=self.reactor.gas,
            recycle_to_feed_ratio=final_recycle_moles / initial_state.moles,
            initial_moles=initial_state.moles,
            final_recycle_moles=final_recycle_moles,
            mass_balance_history=mass_balance_history,
            recycle_ratios=config.recycle_ratios
        )

    def _verify_mass_balance(self, initial_state: ct.Quantity, final_state: ct.Quantity, 
                           recycle_stream: dict, config: ReactorConfig) -> dict:
        """Verify mass balance across the reactor system."""
        mol_weights = {name: self.reactor.gas.molecular_weights[i] 
                      for i, name in enumerate(self.reactor.gas.species_names)}
        
        # Calculate stream properties
        fresh_feed_moles = initial_state.moles
        fresh_feed_mass = initial_state.mass
        recycle_moles = sum(recycle_stream.values())
        recycle_mass = sum(moles * mol_weights[species]
                          for species, moles in recycle_stream.items()
                          if species in mol_weights)
        
        reactor_inlet_moles = fresh_feed_moles + recycle_moles
        reactor_inlet_mass = fresh_feed_mass + recycle_mass
        reactor_outlet_mass = reactor_inlet_mass
        reactor_outlet_moles = reactor_outlet_mass / final_state.mean_molecular_weight
        
        final_outlet_mass = reactor_outlet_mass
        final_outlet_moles = reactor_outlet_moles
        
        for species, recycle_moles in recycle_stream.items():
            final_outlet_mass -= recycle_moles * mol_weights[species]
            final_outlet_moles -= recycle_moles
        
        relative_error = abs(fresh_feed_mass - final_outlet_mass) / fresh_feed_mass
        reactor_error = abs(reactor_inlet_mass - reactor_outlet_mass) / reactor_inlet_mass
        
        print("\nMass Balance Summary:")
        print("┌────────────────┬────────────┬────────────┬────────────┐")
        print("│     Stream     │  Mass (kg) │ Moles (kmol)│ Error (%) │")
        print("├────────────────┼────────────┼────────────┼────────────┤")
        print(f"│ Fresh Feed     │ {fresh_feed_mass:10.4f} │ {fresh_feed_moles:10.4f} │     -      │")
        print(f"│ Recycle        │ {recycle_mass:10.4f} │ {recycle_moles:10.4f} │     -      │")
        print(f"│ Reactor Inlet  │ {reactor_inlet_mass:10.4f} │ {reactor_inlet_moles:10.4f} │     -      │")
        print(f"│ Reactor Outlet │ {reactor_outlet_mass:10.4f} │ {reactor_outlet_moles:10.4f} │ {reactor_error*100:10.2f} │")
        print(f"│ Final Outlet   │ {final_outlet_mass:10.4f} │ {final_outlet_moles:10.4f} │ {relative_error*100:10.2f} │")
        print("└────────────────┴────────────┴────────────┴────────────┘")

        return {
            'streams': {
                'fresh_feed': {'moles': fresh_feed_moles, 'mass': fresh_feed_mass},
                'recycle': {'moles': recycle_moles, 'mass': recycle_mass},
                'reactor_inlet': {'moles': reactor_inlet_moles, 'mass': reactor_inlet_mass},
                'reactor_outlet': {'moles': reactor_outlet_moles, 'mass': reactor_outlet_mass},
                'final_outlet': {'moles': final_outlet_moles, 'mass': final_outlet_mass}
            },
            'relative_error': relative_error,
            'reactor_error': reactor_error,
            'is_balanced': relative_error <= config.mass_balance_tol and reactor_error <= config.mass_balance_tol
        }
