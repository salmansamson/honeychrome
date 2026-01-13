from pathlib import Path
import flowkit as fk
import numpy as np

from instrument_configuration import n_channels_trace, n_time_points_in_event
from settings import adc_channels, magnitude_ceiling

fcs_file = Path(__file__).parent / 'example_for_dummy_acquisition.fcs'

def gaussian_rows_areas(x_grid, areas, mu, sigma):
    """
    Create 2D array where each row is a Gaussian with specified area.

    Parameters:
    x_grid: 1D array of x positions
    areas: 1D array of areas (integral under each Gaussian)
    mu: mean position of Gaussian (same for all)
    sigma: standard deviation (same for all)

    Returns:
    2D array of shape (len(areas), len(x_grid))
    """
    # Calculate the base Gaussian (area = 1)
    base_gaussian = np.exp(-0.5 * ((x_grid - mu) / sigma) ** 2)
    base_gaussian /= (sigma * np.sqrt(2 * np.pi))

    # Scale each row by its area using broadcasting
    # areas[:, None] makes areas a column vector for proper broadcasting
    return areas[:, None] * base_gaussian


class DummyInstrument:
    def __init__(self):
        self.sample = fk.Sample(fcs_file)
        fcs_file_channels = list(self.sample.channels['pnn'])
        area_channels = [s[:-2] for s in fcs_file_channels]
        self.channel_indices = [area_channels.index(channel) for channel in adc_channels]
        self.head = 0
        self.tail = self.sample.event_count
        self.trace_indices = np.arange(n_time_points_in_event)  # x positions
        self.scale = magnitude_ceiling / int(self.sample.metadata['p2r'])

    def generate_traces(self, n):
        # reads events, returns a blob_np
        # note blob_np is 1d numpy array of n * n_channels_trace * n_time_points_in_event

        events = self.sample.get_events('raw')[self.head:self.head+n, self.channel_indices]
        self.head += n
        traces = gaussian_rows_areas(self.trace_indices, events.reshape(-1), n_time_points_in_event//2, 5+2*np.random.rand())
        traces *= self.scale
        traces = traces.astype(np.uint16)
        traces = traces.reshape(-1)
        return traces


if __name__ == '__main__':
    dummy_instrument = DummyInstrument()
    blob_np = dummy_instrument.generate_traces(5)
    print(blob_np)

    traces = blob_np.reshape(5, n_channels_trace, n_time_points_in_event)
    print(dummy_instrument.sample.get_events('raw')[0, dummy_instrument.channel_indices] * dummy_instrument.scale)
    print(traces[0].sum(axis=1))
