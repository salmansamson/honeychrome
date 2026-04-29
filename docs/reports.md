---
layout: default
title: Reports, Exports & Sample Comparison
---
[Cytkit](https://cytkit.com) | [Honeychrome](https://honeychrome.cytkit.com/) 
---

# <img src="/src/honeychrome/view_components/assets/cytkit_web_logo.png" width="60"> Honeychrome

{% include menu.md %}

# Reports, Exports & Sample Comparison
This guide assumes you have already done the following:
- installed Honeychrome using the [executable installers (Windows/Mac/Linux) or Python (cross-platform)](/readme)
- followed at least one of the following examples
  * [Spectral Analysis](/docs/spectral_analysis) 
  * [Conventional Analysis](/docs/conventional_analysis)
  * set up [plots and gates](/docs/cytometry_plots_and_gates) in the unmixed data.

From the unmixed cytometry, Honeychome can: 
- generate a sample report
- export individual figures
- export unmixed FCS files, 
- generate statistical comparisons between samples, as a:
  - bar chart
  - box and whisker chart
  - 1D histogram overlay

{:toc}

## Sample Report
With a sample selected in the sample browser (left pane), click on the "DOCX" button to generate a sample report in DOCX format (or select File menu > Generate Sample Report). The sample report may optionally contain a summary of the raw cytometry data, spectral process and unmixed cytometry data for that sample. (Default is unmixed data and spectral process: see menu Edit > App Configuration.)

The DOCX is saved to the Reports subfolder of the experiment folder. The folder hierarchy of the Reports subfolder mirrors that of the Raw data files. 

From the report, figures and tables may be copied and pasted into other documents using a word processor.

![sample_report_button.png](/assets/sample_report_button.png)

![img.png](/assets/sample_report.png)

## Export Plot / Copy to Clipboard
Right click on an individual plot to copy to clipboard / export to a PNG file.

![export_clipboard_plot.png](/assets/export_clipboard_plot.png)

## Export Unmixed FCS Files
The batch export function (menu bar or File menu > Batch Export FCS) allows export of a set of FCS files (organised by subfolder). Samples may optionally be subsampled (default: 10,000 events, configurable in menu File > App Configuration).
![batch_export_dialog.png](/assets/batch_export_dialog.png)

## Statistical Comparison of Samples
Statistical comparison functions are available in the Statistics tab. 

### Bar Chart / Box and Whisker Chart
Select any sample set / gate / statistic to produce a bar chart or box-and-whisker chart as follows:
![select_bar_chart.png](/assets/select_bar_chart.png)

The following statistics are available:
- % Total Events
- % Parent
- Number of Events
- Mean Intensity (in any channel)

![bar_chart.png](/assets/bar_chart.png)

A box-and-whisker chart compares folders of samples: each subfolder is treated a group, and each sample within it is treated as a repeat:

![box_and_whisker.png](/assets/box_and_whisker.png)

Data can be exported from these plots as an image or CSV file for inspection and plotting in a spreadsheet:

![csv_export.png](/assets/csv_export.png)

### 1D Histogram Overlay
Select any sample set / gate / channel to produce a 1D histogram overlay comparison as follows. 

![select_1d_hist_overlay.png](/assets/select_1d_hist_overlay.png)

![statistical_comparison_of_samples.png](/assets/statistical_comparison_of_samples.png)