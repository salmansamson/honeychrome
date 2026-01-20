from PyInstaller.utils.hooks import collect_data_files

# Collect all data files from flowkit package
datas = collect_data_files('flowkit')

print("Including flowkit data files:", datas)