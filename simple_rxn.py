import cantera as ct

# Load the original mechanism
gas = ct.Solution('aramco.yaml')

# Get all species containing only C, H, N
filtered_species = [sp.name for sp in gas.species() 
                   if all(elem in ['C', 'H', 'N'] for elem in sp.composition.keys())]

# Create a new mechanism with filtered species
filtered_mech = ct.Solution(thermo='IdealGas',
                          kinetics='GasKinetics',
                          species=[sp for sp in gas.species() if sp.name in filtered_species])

# Export the filtered mechanism
filtered_mech.write_yaml('aramco_small.yaml')