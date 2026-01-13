'''
Set up entire workflow before setting up GUI

Use Oliver Burton's data:

Spectral Cytometry: unmixing autofluorescence
https://data.mendeley.com/datasets/y2zp5xx2hg/1
Tissue autofluorescence (high dimensional)
https://data.mendeley.com/datasets/ws9jwvbfmj/1

Use Flowkit
'''
from email.contentmanager import raw_data_manager

#%% load libraries, functions, etc

import numpy as np
import pandas as pd
import flowkit as fk
import os
import glob
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import PCA
import matplotlib as mpl
mpl.use('tkagg')

from copy import deepcopy
from time import perf_counter
from time import time as timestamp

# from pympler import asizeof
import seaborn as sns

from matplotlib import pyplot as plt
#plt.ion()

def all_same(lst):
    if not lst:  # Handle empty list
        return True  # or False, depending on your needs
    return all(x == lst[0] for x in lst)

base_directory = r'/home/ssr/spectral_cytometry'

#%% define data source root directory

experiment_root_directory = r'/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed'
os.chdir(experiment_root_directory)
# Assume standard structure:
# - Raw
# -- Cell controls
# -- Bead controls
# - Samples
# -- AF controls
# -- Single stain controls
# -- Group / sample
raw_cell_controls = glob.glob('Raw/Cell controls/**/*.fcs', recursive=True)
raw_bead_controls = glob.glob('Raw/Bead controls/**/*.fcs', recursive=True)
raw_af_controls = glob.glob('Raw/Samples/AF controls/**/*.fcs', recursive=True)
raw_controls = raw_cell_controls + raw_bead_controls + raw_af_controls

raw_samples = glob.glob('Raw/Samples/**/*.fcs', recursive=True)
raw_samples = [item for item in raw_samples if item not in raw_af_controls]
all_samples = raw_controls + raw_samples


#%% create flowkit session for all raw FCS files - print name, datetime, number of events, file location
# raw_session = fk.Session(fcs_samples = all_samples) #### slow, uses a lot of memory!
# asizeof.asizeof(raw_session)
# all_sample_channels = {}
# for sample_id in raw_session.get_sample_ids():
#     sample = raw_session.get_sample(sample_id)
#     all_sample_channels[sample_id] = list(sample.channels.pnn)
# all_same(list(all_sample_channels.values()))

#%% load samples one by one, print name, datetime, number of events, file location
all_sample_meta = {}
all_sample_channels = {}
all_sample_nevents = {}
for sample_path in raw_controls:
    sample = fk.Sample(sample_path)
    all_sample_meta[sample_path] = sample.get_metadata()
    all_sample_channels[sample_path] = sample.channels
    all_sample_nevents[sample_path] = sample.event_count
    print([all_sample_meta[sample_path][key] for key in ['fil', 'proj', 'tubename', 'groupname', 'platename', 'tot', 'date', 'etim']])

# extract channel names - check that channel names are consistent
all_sample_pnn = [list(all_sample_channels[sample_path].pnn) for sample_path in raw_controls]
print(all_same(all_sample_pnn)) # True if all channel names the same

# check whether any transforms and gates are defined
# create an instrument settings object with channels and ranges
raw_settings = {
    'pnn': all_sample_pnn[0],
    'fluorescence_channel_range': 4194304,
    'time_channel_id': sample.time_index,
    'scatter_channel_ids': sample.scatter_indices,
    'fluorescence_channel_ids': sample.fluoro_indices
}

#%% auto set positive gate as range gate of top 100 events in each channel
# auto create spectral model table
# (sample name, label, sample path, particle_type (cells/beads), control_type (positive only, positive and negative, autofluorescence), gate channel

plt.figure()
all_sample_gates = {}
gating_strategy = fk.GatingStrategy()
spectral_model = []

fsc_index = sample.scatter_indices[3]
ssc_index = sample.scatter_indices[1]

dim_x = fk.Dimension(raw_settings['pnn'][fsc_index],
                     range_min=0, range_max=4194304)
dim_y = fk.Dimension(raw_settings['pnn'][ssc_index],
                     range_min=0, range_max=4194304)
base_gate_label = 'Cells'
base_gate = fk.gates.RectangleGate(base_gate_label, dimensions=[dim_x, dim_y])
gating_strategy.add_gate(base_gate, gate_path=('root',))

# prioritise cell controls
for sample_path in raw_cell_controls + raw_bead_controls:
# for sample_path in [raw_cell_controls[13]]:
    if sample_path in raw_cell_controls:
        particle_label = 'Cells'
    else:
        particle_label = 'Beads'

    tubename = all_sample_meta[sample_path]['tubename']
    label = tubename.replace('('+particle_label+')', '').strip()
    # discard if label is already in spectral model
    if label in [component['label'] for component in spectral_model]:
        continue

    sample = fk.Sample(sample_path)
    # gate first by cells
    base_event_mask = gating_strategy.gate_sample(sample).get_gate_membership('Cells')
    base_event_mask_indices = np.where(base_event_mask)[0]

    pca = PCA(n_components=1)
    event_data_fluorescence = sample.get_events('raw')[base_event_mask][:,raw_settings['fluorescence_channel_ids']]
    pca.fit(event_data_fluorescence)
    print([label, pca.explained_variance_ratio_[0]])
    plt.plot(pca.components_[0], label=label)

    # get top n events in principle axis
    events_transformed_to_pca = pca.transform(event_data_fluorescence).flatten()
    n_to_gate = 100
    # More efficient for large arrays - doesn't fully sort
    indices_top_n_events = np.argpartition(events_transformed_to_pca, -n_to_gate)[-n_to_gate:]
    # Sort the top 100 indices by value (descending)
    indices_top_n_events = base_event_mask_indices[indices_top_n_events[np.argsort(events_transformed_to_pca[indices_top_n_events])][::-1]]

    # define gate
    n_matches_per_fluorescence_channel = np.zeros(len(raw_settings['pnn']))
    matches_per_fluorescence_channel = {}
    for channel_id in raw_settings['fluorescence_channel_ids']:
        fl = sample.get_events('raw')[base_event_mask, channel_id]
        indices_top_n_events_fluorescence_channels = base_event_mask_indices[np.argpartition(fl, -n_to_gate)[-n_to_gate:]]
        matches_per_fluorescence_channel[channel_id] = list(set(indices_top_n_events) & set(indices_top_n_events_fluorescence_channels))
        n_matches_per_fluorescence_channel[channel_id] = len(matches_per_fluorescence_channel[channel_id])
    # # in which single channel are most of those top n events at the top?
    # channel_id_best_match = np.argmax(n_matches_per_fluorescence_channel)
    # or just peak of spectral profile (PCA component)
    channel_id_best_match = raw_settings['fluorescence_channel_ids'][np.argmax(pca.components_[0])]


    best_match = n_matches_per_fluorescence_channel[channel_id_best_match]
    fl = sample.get_events('raw')[matches_per_fluorescence_channel[channel_id_best_match],channel_id_best_match]
    print([label, raw_settings['pnn'][channel_id_best_match], best_match])

    dim_x = fk.Dimension(raw_settings['pnn'][channel_id_best_match],
                         range_min=fl.min(), range_max=fl.max())
    positive_gate_label = 'Positive ' + label
    positive_gate = fk.gates.RectangleGate(positive_gate_label, dimensions=[dim_x])

    # all_sample_gates[sample_path] = positive_gate
    # gating_strategy.add_gate(positive_gate, ('root',), sample_id=sample_path)

    # # create a copy of the gating strategy for each positive gate separately
    # all_sample_gates[sample_path] = deepcopy(gating_strategy)
    # all_sample_gates[sample_path].add_gate(positive_gate, ('root',), sample_id=sample_path)

    # add all positive gates to the same gating strategy: they are distinguished by their label and by the sample_id that they refer to
    gating_strategy.add_gate(positive_gate, gate_path=('root', base_gate_label))
    # gating_strategy.add_gate(positive_gate, gate_path=('root',))
    # gating_strategy.add_gate(positive_gate, gate_path=('root', base_gate_label), sample_id=sample_path) # needs to be done twice to be a custom sample gate
    # gating_strategy.add_gate(positive_gate, gate_path=('root',), sample_id=sample_path) # needs to be done twice to be a custom sample gate
    all_sample_gates[sample_path] = 'Positive ' + label

    report = gating_strategy.gate_sample(sample).report.set_index('gate_name')
    print(report.loc[positive_gate_label]['count']) # check gating

    spectral_model += [{
        'label': label,
        'sample_name': all_sample_meta[sample_path]['fil'],
        'sample_path': sample_path,
        'particle_type': particle_label,
        'control_type': 'Positive Only',
        'gate_channel': channel_id_best_match,
        'gate_label': positive_gate_label
    }]

### hold this bit until Oliver can tell me what to do
# for sample_path in raw_af_controls:
#     pass

# spectral_model += [{'sample_name': [], 'label': [], 'sample_path': [], 'particle_type': [], 'control_type': [], 'gate_channel': []}]
#spectral_model = pd.DataFrame(spectral_model, index='sample_path')
spectral_model = pd.DataFrame(spectral_model)
spectral_model = spectral_model.set_index('label')

plt.legend(loc='best')

print(gating_strategy.get_gate_hierarchy())

#%% present spectral profiles
plt.figure()
profiles = {}

start = perf_counter()

for label in spectral_model.index:
    print(spectral_model.loc[label])
    sample_path = spectral_model.loc[label,'sample_path']
    sample = fk.Sample(sample_path)

    # # get events in gate -- if all have separate gating strategies
    # event_mask = all_sample_gates[sample_path].gate_sample(sample).get_gate_membership(
    #     all_sample_gates[sample_path].get_gate_ids()[0][0]
    # )

    # # get events in gate
    # event_mask = gating_strategy.gate_sample(sample).get_gate_membership(positive_gate_label)

    # get events in gate - generate temporary gating strategy for one sample only (faster)
    positive_gate_label = spectral_model.loc[label]['gate_label']
    gate_ids = list(gating_strategy.find_matching_gate_paths(positive_gate_label)[0]) + [positive_gate_label]
    temp_gating_strategy = fk.GatingStrategy()
    for n, gate_id in enumerate(gate_ids):
        if gate_id != 'root':
            temp_gating_strategy.add_gate(gating_strategy.get_gate(gate_id), gate_path=tuple(gate_ids[:n]))

    event_mask = temp_gating_strategy.gate_sample(sample).get_gate_membership(positive_gate_label)
    print(event_mask.sum())

    profile = sample.get_events('raw')[event_mask].mean(axis=0)
    profile = profile[raw_settings['fluorescence_channel_ids']]
    profile = profile/np.sqrt((profile**2).sum()) # sum of squares normalisation
    #profile = profile/profile.max() # max normalisation
    #profile = profile/profile.mean() # sum normalisation

    profiles[sample_path] = profile
    plt.plot(profile, label=label)

plt.legend(loc='best')

end = perf_counter()
print(f"Execution time: {end - start:.6f} seconds")


profiles = pd.DataFrame(profiles)
#%% present similarity matrix
plt.figure()
similarity_matrix = cosine_similarity(np.array(profiles).T)
sns.heatmap(similarity_matrix, annot=True, xticklabels=spectral_model['label'], yticklabels=spectral_model['label'])

#%% calculate unmixing matrix
#channels = [0, 1, 5, 6, 7, 8, 9, 10, 11]
variance_per_detector = np.ones(len(raw_settings['fluorescence_channel_ids'])) # trivial example... try something better like cv on each detector for brightest fluorophores?
Omega_inv = np.diag(1 / variance_per_detector) # This is our weight matrix
# Unmixing matrix W = (Mᵀ • Ω⁻¹ • M)⁻¹ • Mᵀ • Ω⁻¹
# M = np.array(profiles.iloc[:,channels]).T
M = np.array(profiles).T
unmixing_matrix = np.linalg.inv(M @ Omega_inv @ M.T) @ M @ Omega_inv # W matrix in Novo paper

# profile_test = profiles.iloc[:,0]
# F = unmixing_matrix @ profile_test
# fig, ax = plt.subplots(3)
# ax[0].plot(profiles)
# ax[1].plot(profile_test)
# ax[2].plot(F)

fig, ax = plt.subplots(2)
ax[0].plot(profiles)
for profile_test in M:
    F = unmixing_matrix @ profile_test
    ax[1].plot(F)


#%% present unmixing matrix

n_scatter_channels = len(raw_settings['scatter_channel_ids'])
n_fluorophore_channels = len(spectral_model['label'])

unmixed_settings = {
    'pnn': ['Time'] + [raw_settings['pnn'][n]for n in raw_settings['scatter_channel_ids']] + list(spectral_model['label']),
    'fluorescence_channel_range': 4194304,
    'time_channel_id': 0,
    'scatter_channel_ids': list(range(1, 1+n_scatter_channels)),
    'fluorescence_channel_ids': list(range(1+n_scatter_channels, 1+n_scatter_channels+n_fluorophore_channels))
}

plt.figure()
sns.heatmap(unmixing_matrix, annot=True, xticklabels=[raw_settings['pnn'][n] for n in raw_settings['fluorescence_channel_ids']], yticklabels=spectral_model['label'])

#%% save spectral model plus spectral profiles, similarity matrix, unmixing matrix

import pickle

# Save
spectral_configuration = {
    'spectral_model': spectral_model,
    'profiles': profiles,
    'similarity_matrix': similarity_matrix,
    'unmixing_matrix': unmixing_matrix
}
with open('spectral_configuration.pkl', 'wb') as f:
    pickle.dump(spectral_configuration, f)

#%% save spectral model to spectral library
import sqlite3

library_deposit = spectral_model.copy()
library_deposit['experiment_root_directory'] = experiment_root_directory  # Same value for all rows
library_deposit['timestamp'] = timestamp()  # Same value for all rows

library_path = base_directory + '/spectral_controls_library.db'
# conn = sqlite3.connect(library_path)
# library_deposit.to_sql('spectral_controls_history', conn, if_exists='append', index=True, index_label='label')
# conn.close()
with sqlite3.connect(library_path) as conn:
    library_deposit.to_sql('spectral_controls_history', conn, if_exists='append', index=True, index_label='label')

# Load
# conn = sqlite3.connect(library_path)
# history = pd.read_sql('SELECT * FROM spectral_controls_history', conn)
# conn.close()
with sqlite3.connect(library_path) as conn:
    history = pd.read_sql('SELECT * FROM spectral_controls_history', conn)

#%% load current sample (raw)
raw_sample_path = 'Raw/Samples/Spleen/A1 Spleen_WT_001_Samples.fcs'
raw_sample = fk.Sample(raw_sample_path)
time_data = raw_sample.get_events('raw')[:,raw_settings['time_channel_id']].reshape(-1,1)
scatter_data = raw_sample.get_events('raw')[:,raw_settings['scatter_channel_ids']]
raw_fluorescence_data = raw_sample.get_events('raw')[:,raw_settings['fluorescence_channel_ids']]

#%% unmix current sample
# create unmixed channels and dimensions
unmixed_fluorescence_data = raw_fluorescence_data @ unmixing_matrix.T

# define fine tuning matrix as compensation matrix
compensation = np.eye(n_fluorophore_channels)
compensated_fluorescence_data = unmixed_fluorescence_data @ compensation.T

# display NxN plots
compensated_fluorescence_dataframe = pd.DataFrame(compensated_fluorescence_data, columns=[unmixed_settings['pnn'][n] for n in unmixed_settings['fluorescence_channel_ids']])
sns.pairplot(compensated_fluorescence_dataframe.iloc[:1000,:5])


#%% create sample object for unmixed data with compensation and save FCS file - this is slow so only do this at end
event_data = np.hstack((time_data, scatter_data, unmixed_fluorescence_data))

sample = fk.Sample(
    event_data,
    sample_id=raw_sample.id,
    channel_labels=unmixed_settings['pnn'],
    compensation=compensation,
    subsample=10000
)

# # calculate compensation
# sample.apply_compensation(compensation)

os.makedirs('Exported', exist_ok=True) #create exports folder if it doesn't exist
sample.export('Exported/'+raw_sample.id, source='comp', include_metadata=True)


#%% calculate all unmixed channels on all samples
# create flowkit session object with all unmixed channels on all samples (excluding controls?)
# save all unmixed data


