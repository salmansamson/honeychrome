'''
Spectral library
-loads spectral controls database
-deposits current controls
-searches database for fluorophore
-retrieves control from databases
'''
import sqlite3
from time import time as timestamp
from pathlib import Path
import json

from honeychrome.settings import experiments_folder, library_file

base_directory = Path.home() / experiments_folder

class SpectralLibrary:
    def __init__(self):

        self.library_path = base_directory / library_file


    def deposit_control_with_profile_and_experiment_dir(self, control, profile_dict, experiment_dir):
        # save spectral model to spectral library
        from pandas import DataFrame
        library_deposit = DataFrame([control])
        library_deposit = library_deposit.set_index('label')
        library_deposit['profile_dict'] = json.dumps(profile_dict)
        library_deposit['experiment_root_directory'] = experiment_dir  # Same value for all rows
        library_deposit['timestamp'] = timestamp()

        with sqlite3.connect(self.library_path) as conn:
            library_deposit.to_sql('spectral_controls_history', conn, if_exists='append', index=True, index_label='label')

    def load_history(self):
        from pandas import read_sql
        with sqlite3.connect(self.library_path) as conn:
            history = read_sql('SELECT * FROM spectral_controls_history', conn)

        return history

    def search_for_label(self, label):
        from pandas import read_sql
        with sqlite3.connect(self.library_path) as conn:
            results = read_sql('SELECT * FROM spectral_controls_history WHERE label = :label ORDER BY timestamp DESC', conn, params={'label': label}).to_dict('index')

        return results


if __name__ == '__main__':
    spectral_library = SpectralLibrary()

    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_dir = str(experiment_name)

    control = {
        'label': 'PE-Fire 810',
        'control_type': 'Single Stained Spectral Control',
        'particle_type': 'Cells',
        'gate_channel': "B8",
        'sample_name': 'PE-Fire 810 (Cells)',
        'sample_path': '/home/ssr/spectral_cytometry/20240620 Spectral Symposium-poor cell unmixed/Raw/Cell controls/Reference Group/G1 PE-Fire 810 (Cells)_Cell controls.fcs',
        'gate_label': 'Positive PE-Fire 810',
    }

    profile = {"UV1-A": 0.03317088990796552, "UV2-A": 0.05332927747947873, "UV3-A": 0.06113627449460505, "UV4-A": 0.07562920902567627, "UV5-A": 0.10239516171123453, "UV6-A": 0.17884020224051614, "UV7-A": 0.4070593835378479, "UV8-A": 0.3251922838925199, "UV9-A": 0.4663197008183471, "UV10-A": 0.16127642599364841, "UV11-A": 0.1170627263961532, "UV12-A": 0.08516685916575374, "UV13-A": 0.09204708926555366, "UV14-A": 0.10575895742335219, "UV15-A": 0.09967360871002572, "UV16-A": 0.087133842605792, "V1-A": 0.054838881057859584, "V2-A": 0.18712130363806184, "V3-A": 0.31455028961447506, "V4-A": 0.3931481959256897, "V5-A": 0.6952820999333164, "V6-A": 0.6910806393853435, "V7-A": 1.0, "V8-A": 0.871107479939216, "V9-A": 0.6787525608697828, "V10-A": 0.7655194450935996, "V11-A": 0.4876695135186632, "V12-A": 0.3260953009137202, "V13-A": 0.3453660488082803, "V14-A": 0.3335438564065162, "V15-A": 0.32705035155045853, "V16-A": 0.1926488080970195, "B1-A": 0.399995199063976, "B2-A": 0.4332740869374692,
        "B3-A": 0.5669157225796915, "B4-A": 0.4849066655653393, "B5-A": 0.4454355715269352, "B6-A": 0.3757291198503883, "B7-A": 0.3350683125289501, "B8-A": 0.26277311553440275, "B9-A": 0.27916551929398026, "B10-A": 0.19017513615065704, "B11-A": 0.1373464545930562, "B12-A": 0.13755818974693199, "B13-A": 0.1225141524569433, "B14-A": 0.16037445016263144, "YG1-A": 0.17242365373756563, "YG2-A": 0.1628721068343792, "YG3-A": 0.1859047459491845, "YG4-A": 0.24059992340654712, "YG5-A": 0.20362953232961364, "YG6-A": 0.21159159612197745, "YG7-A": 0.29608678275554084, "YG8-A": 0.18243504608224528, "YG9-A": 0.1651451697652217, "YG10-A": 0.12024122461683524, "R1-A": 0.04314357942295587, "R2-A": 0.07686995313316748, "R3-A": 0.0990073230517106, "R4-A": 0.10862371622487586, "R5-A": 0.09984460034361178, "R6-A": 0.09303464674835321, "R7-A": 0.11184608975521207, "R8-A": 0.0714110332495394}

    spectral_library.deposit_control_with_profile_and_experiment_dir(control, profile, experiment_dir)

    history = spectral_library.load_history()
    print(history.to_string())

    results = spectral_library.search_for_label('PE-Fire 810')
    print(results)