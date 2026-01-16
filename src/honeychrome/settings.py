'''
These are the default settings for the honeychrome software
'''
from PySide6.QtCore import QSettings

### folder in home directory where experiments will be stored
experiments_folder = 'Experiments'
file_extension = 'kit'
graphics_export_format = 'png' # png, pdf or svg
graphics_export_formats = ['png', 'pdf', 'svg']
sample_name_source = 'filename'
metadata_sample_name_sources = ['tubename', 'fil']

### file in experiments folder where spectral library database will be stored
library_file = 'spectral_controls_library.db'

### define default channels for trace analyser and experiment model - these should match the channels in the instrument
max_events_in_cache = 10_000_000
adc_channels = ['FSC', 'SSC', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14']
trigger_channel = 'FSC'
area_channels = ['FSC', 'SSC', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14'] # make sure there is equal number to n_channels_trace in instrument config
height_channels = ['FSC']
width_channels = ['FSC']
scatter_channels = ['FSC', 'SSC']
fluorescence_channels = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14']
event_channels_pnn = ['Time', 'event_id'] + [c + '-A' for c in area_channels] + [c + '-H' for c in height_channels] + [c + '-W' for c in width_channels]
n_channels_per_event = len(event_channels_pnn)
use_dummy_instrument = True

### settings for controller and gui
default_gains_immuno = {'B1':1., 'B2':1., 'B3':1., 'B4':1., 'B5':1., 'B6':1., 'B7':1., 'B8':1., 'B9':1., 'B10':1., 'B11':1., 'B12':1., 'B13':1., 'B14':1.}
default_gains_xfp = {'B1':1., 'B2':1., 'B3':1., 'B4':1., 'B5':1., 'B6':1., 'B7':1., 'B8':1., 'B9':1., 'B10':1., 'B11':1., 'B12':1., 'B13':1., 'B14':1.}
cytometry_plot_width_target = 350 # pixels
cytometry_plot_width_export = 70 # mm
tile_size_nxn_grid = 100 # pixels
roi_handle_size = 12 # pixels
colormap_name = 'rainbow4' # Choose a Colorcet colormap (e.g., 'fire', 'bgy', 'rainbow')
colourmap_choice = ['bjy', 'kbc', 'bgy', 'bmy', 'CET_CBD2', 'rainbow', 'rainbow4', 'fire'] # use linear or rainbow colourmaps
report_include_raw = False
report_include_unmixed = True
report_include_process = True
wheel_speed = 0.002
heading_style = """
QLabel {
    font-size: 18px;
    padding-top: 16px;
}
"""
live_data_process_repeat_time = 0.5 #s
hist_bins = 200 # for displaying histograms
label_offset_default = (0, -0.03) # for gate labels
subsample = 10_000 # for exporting FCS files

line_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
          '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5', '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
          '#393b79', '#637939', '#8c6d31', '#843c39', '#7b4173', '#5254a3', '#6b6ecf', '#9c9ede', '#31a354', '#b5cf6b',
          '#e7ba52', '#ce6dbd', '#de9ed6', '#e7969c', '#7b4173']

spectral_positive_gate_percent = 5 # take the top few percent of events
spectral_negative_gate_percent = 25 # take the bottom few percent of events

spectral_model_column_labels = {
    "label": "Label",
    "control_type": "Control Type",
    "particle_type": "Particle Type",
    "gate_channel": "Major Channel",
    "sample_name": "Sample Name",
    "gate_label": "Positive Gate"
}

### put together channel_dict for controller + trace analyst
channel_dict = {'adc_channels': adc_channels, 'trigger_channel': trigger_channel, 'area_channels': area_channels,
                'height_channels': height_channels, 'width_channels': width_channels, 'scatter_channels': scatter_channels,
                'fluorescence_channels': fluorescence_channels, 'event_channels_pnn': event_channels_pnn, 'n_channels_per_event':n_channels_per_event}

### settings for trace analyser
analyser_target_repeat_time = 0.25 # seconds

### define settings for experiment model
time_channel_id = event_channels_pnn.index('Time')
event_id_channel_id = event_channels_pnn.index('event_id')

pnn_stripped = event_channels_pnn.copy()
for suffix in ['-A', '-H', '-W']:
    pnn_stripped = [c.removesuffix(suffix) if c.endswith(suffix) else c for c in pnn_stripped]

scatter_channel_pnn = [c for c in event_channels_pnn if any(b in c for b in scatter_channels)]
scatter_channel_ids = [event_channels_pnn.index(c) for c in scatter_channel_pnn]
n_scatter_channels = len(scatter_channel_ids)
fluorescence_channels_pnn = [c for c in event_channels_pnn if any(b in c for b in fluorescence_channels)]
fluorescence_channel_ids = [event_channels_pnn.index(c) for c in fluorescence_channels_pnn]
n_fluorophore_channels = len(fluorescence_channel_ids)

width_ceiling = 50_000 # nanoseconds
default_ceiling = 60
magnitude_ceiling = 2**18 # according to convention
magnitude_ceilings = ['2**18 = 262144', '2**22 = 4194304', '2**24 = 16777216'] # 2**16 = 65536, 2**18 = 262144, 2**22 = 4194304, 2**24 = 16777216
magnitude_ceilings_int = [262144, 4194304, 16777216]

linear_a = 100
logicle_w = 0.5
logicle_m = 4.5
logicle_a = 0
log_m = 6

raw_settings = {
    'raw_samples_subdirectory': 'Raw',
    'single_stain_controls_subdirectory': 'Raw/Single stain controls',
    'area_channels': area_channels,
    'height_channels': height_channels,
    'width_channels': width_channels,
    'scatter_channels': scatter_channels,
    'fluorescence_channels': fluorescence_channels,
    'event_channels_pnn': event_channels_pnn,
    'width_ceiling': width_ceiling,
    'magnitude_ceiling': magnitude_ceiling,
    'default_ceiling': default_ceiling,
    'time_channel_id': time_channel_id,
    'event_id_channel_id': event_id_channel_id,
    'scatter_channel_ids': scatter_channel_ids,
    'n_scatter_channels': n_scatter_channels,
    'fluorescence_channel_ids': fluorescence_channel_ids,
    'n_fluorophore_channels': n_fluorophore_channels
}

unmixed_settings = {
    'unmixed_samples_subdirectory': 'Unmixed',
    'area_channels': None,
    'height_channels': None,
    'width_channels': None,
    'scatter_channels': None,
    'fluorescence_channels': None,
    'event_channels_pnn': None,
    'width_ceiling': None,
    'magnitude_ceiling': None,
    'time_channel_id': None,
    'event_id_channel_id': None,
    'scatter_channel_ids': None,
    'n_scatter_channels': None,
    'fluorescence_channel_ids': None,
    'n_fluorophore_channels': None
}

settings_default = {
    'raw':raw_settings,
    'unmixed':unmixed_settings,
}

samples_default = {
    'single_stain_controls': [],
    'all_samples': {},
    'all_sample_nevents': {}
}

process_default = {
    'base_gate_priority_order': ['Singlets', 'Cells', 'root'],
    'fluorescence_channel_filter': 'area_only', # or all fluorescence
    'spectral_model': [],
    'profiles': {},
    'negative_type': 'internal', # or unstained
    'similarity_matrix': None,
    'unmixing_matrix': None,
    'spillover': None
}

cytometry_default = {
    'raw_gating': None,
    'raw_transforms': None,
    'raw_plots': None,
    'gating': None,
    'transforms': None,
    'plots': None
}

# retrieve from QSettings
q_settings = QSettings("honeychrome", "app_configuration")
colourmap_name_retrieved = str(q_settings.value("colourmap", colormap_name))
graphics_export_format_retrieved = str(q_settings.value("graphics_export_format", graphics_export_format))
cytometry_plot_width_target_retrieved = q_settings.value("cytometry_plot_size", cytometry_plot_width_target, type=int)
tile_size_nxn_grid_retrieved = q_settings.value("nxn_tile_size", tile_size_nxn_grid, type=int)
subsample_retrieved = q_settings.value("subsample_number", subsample, type=int)
hist_bins_retrieved = q_settings.value("histogram_resolution", hist_bins, type=int)

trigger_channel_retrieved = str(q_settings.value("trigger_channel", trigger_channel))  # there can only be one trigger channel
width_channel_retrieved = str(q_settings.value("width_channel", width_channels[0]))  # there can be more than one width channel, but currently only allowing one
height_channel_retrieved = str(q_settings.value("height_channel", height_channels))  # there can be more than one height channel, but currently only allowing one
use_dummy_instrument_retrieved = q_settings.value("use_dummy_instrument", use_dummy_instrument, type=bool)

spectral_positive_gate_percent_retrieved = q_settings.value("spectral_positive_gate_percent", spectral_positive_gate_percent, type=int)
spectral_negative_gate_percent_retrieved = q_settings.value("spectral_negative_gate_percent", spectral_negative_gate_percent, type=int)

report_include_raw_retrieved = q_settings.value("report_include_raw", report_include_raw, type=bool)
report_include_unmixed_retrieved = q_settings.value("report_include_unmixed", report_include_unmixed, type=bool)
report_include_process_retrieved = q_settings.value("report_include_process", report_include_process, type=bool)