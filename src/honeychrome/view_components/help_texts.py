process_help_text = '''
<h3>Spectral Process Help</h3>
<p>
Use the Spectral Model Editor to specify the spectral model, for both spectral and conventional cytometry. Single stained controls can be set automatically (see Auto Generate below).
The spectral model should consist of a set of "controls", where each may be of the following <i>control types</i>:
</p>

<ul>
<li>
<b>Single Stained Control:</b> 
this is a sample of beads or cells labelled with one fluorophore only, or autofluorescence only. 
Single stained controls can be set automatically (see Auto Generate below).
To set each single stained control manually, edit the <i>label</i> (e.g. CD4-FITC or Unstained), 
set <i>particle type</i> to cells or beads, and select the control sample's FCS file from the pull-down menu under </i>sample name</i>, 
which lists all FCS files within the Single Stain Controls subfolder. Under <i>positive gate</i>, select the gate that marks the positive events. 
</li>

<li>
<b>Single Stained Control from Library:</b> 
if the required single stained control sample is not present in the current experiment, it may be loaded from previous experiments, if available. 
(Note that all single stained spectral controls are stored in the <tt>spectral_controls_library.db</tt> database in the Experiments folder.) 
Enter the <i>label</i> to search for a match in the database (exact matches only).
</li>

<li>
<b>Channel Assignment:</b> 
in the absence of single stained spectral controls, you may assign a channel directly to a label. 
Each channel assignment is equivalent to assigning a label name to a channel name, or setting the spectral profile to a delta function 
(i.e. intensity = 1 for the <i>major channel</i>, 0 for all other channels). 
Normally, this is only applicable in conventional cytometry with a low number of fluorophores, where you can either compensate manually or ignore compensation.
</li>
</ul>

<h4>How to use <i>Auto Generate Spectral Controls</i></h4>
<p>
This function parses the names of the FCS files in the single stain controls and builds the spectral model automatically. 
The single stain controls subfolder (default: <tt>Raw/Single stain controls</tt>) should include the full set of controls including one named "Unstained". 
</p>

<ol>
<li>
The single stained controls names should start with "Label (Cells)..." or "Label (Beads)". 
(If the name does not contain the particle type, "Cells" is assumed.)
Each is processed to find the fluorescence channel with the largest variation according to that label ("major channel"). 
A positive gate is assigned to the brightest events and a negative gate to the dimmest (percentages are set in Application Configuration; 
default 5% brightest and 25% dimmest). Positive and negative gates are added to the raw cytometry plots as appropriate. 
Select one or more controls in the spectral model to inspect their spectra in the profiles viewer below, or select all / none to inspect all spectra.
</li>

<li>
The spectral profiles use <i>Internal Negatives</i> by default, i.e. the profile is defined as the mean fluorescence of the positively gated sample, 
minus the fluorescence of the negatively gated sample, normalised to peak intensity = 1.
An alternative (better) negative is the <i>Unstained Negative</i>. I.e. the profile is defined as the mean fluorescence of the positively gated sample, 
minus the fluorescence of the negatively gated <i>unstained</i> sample. "Pos Unstained" and "Neg Unstained" gates are added to the raw gating if you didn't already create them.
</li>

<li>
If any singly stained spectral control is missing, you may load it from previous experiments (if an exact match is available). 
Select <i>control type</i> as "Single Stained Control from Library", and enter the label name. 
Exact matches from previously processed data will be returned under <i>sample name</i>.
</li>
</ol>

<h4>Profiles Viewer, Similarity Matrix, Hotspot Matrix, Unmixing Matrix</h4>
<p>
The spectral profiles are displayed in the profiles viewer; the similarity matrix, hotspot matrix and unmixing matrix are also calculated and displayed. 
Selecting one or more labels shows only the relevant profiles and rows of the similarity matrix, unmixing matrix, spillover matrix and NxN plots.
</p>

<h4>Spillover, Compensation, Fine-Tuning and NxN Plots</h4>
<p>
In addition to the non-square unmixing matrix, a square spillover matrix is defined, which can be used for fine tuning in spectral cytometry or manual compensation in conventional cytometry. 
The initial values of spillover matrix are 0 for all non-diagonal elements (1 for diagonal elements). 
</p>

<p>
The spillover matrix can be edited by double clicking on the relevant cell. Alternatively it can be adjusted by rolling the mouse wheel on the spillover matrix or the corresponding tile of the NxN plots.
</p>

<p>
2D histograms of all pairwise combinations of fluorophores (for the current sample, if selected) are displayed in the NxN plots, 
and can be used to inspect the unmixing process and look for issues.
</p>



<h4>Further Reading and Background</h4>

<p>
Honeychrome currently generates an unmixing matrix using only the ordinary least squares (OLS) method, which is the mathematically simplest spectral 
unmixing algorithm [1]. Nevertheless, good results can be obtained with careful selection of clean single stained controls, one or more representative unstained
negatives, and sanity checking of the profiles, similarity matrix, unmixing matrix and NxN plots [2]. 
Spectral unmixing is an area of active development, with much more sophisticated algorithms now available that take proper account of errors in the controls and 
sources of autofluorescence [2]. 
Highly recommended is the Colibri Cytometry blog <a href="https://www.colibri-cytometry.com/post/what-s-an-unmixing-matrix">What's an Unmixing Matrix?</a>.
The similarity and hotspot matrices are defined according to [3].
</p>
<p>
References:<br/>
[1]<a href="https://onlinelibrary.wiley.com/doi/full/10.1002/cyto.a.22272">Novo et al. 2013</a><br/>
[2]<a href="https://www.biorxiv.org/content/10.1101/2025.10.27.684855v1.full">Burton et al. 2025</a><br/>
[3]<a href="https://www.biorxiv.org/content/10.1101/2025.04.17.649396v2.full">Mage et al. 2025</a><br/>
</p>
'''

nxn_help_text = '''
<h3>Select any sample from the sample browser to view it in the NxN plots below.</h3>
<h5>Select from the sample browser on the left, not the spectral model above.</h5>
<ul>
<li>If your panel is large, select one or more rows in the editor above, so that the corresponding rows of the NxN array are plotted below. This makes the plots easier to find, quicker to plot, and quicker to fine-tune.</li>
<li>If no labels are selected above, the full array of NxN plots will be calculated. <b>Warning: this is slow if N is large!</b> If you are using a 60-colour panel, that means calculating 1800 2D histograms at once.</li>
<li>Click to select a cell and roll scroll wheel to adjust spillover (fine tuning) (row label spills into column labels)</li>
<li>Hover to inspect spillover of each cell in the array</li>
</ul>
'''

autospectral_af_help_text = '''
<h5>This is an optional enhancement of the spectral process, which implements the autofluorescence (AF) extraction part of the AutoSpectral package (AutoSpectral AF).</h5>
<p>By following the steps below, you can extract each cell’s individual autofluorescent background in a manner specific to that cell, producing better unmixing with less spread.</p>
<ol>
<li>Extract AF profile from an unstained sample. This can be repeated for each unstained control that you have available, generating multiple AF profiles. </li>
<li>Only unstained cell control samples will appear as options. Mark your unstained samples by right-clicking on the sample and selecting "Mark as Unstained".</li>
<li>Default: 200 clusters (duplicates will be removed, so you will see fewer). After extraction, the clusters can be inspected by clicking on the Stored AF Profiles list.</li>
<li>Assign the AF profiles to Samples. Each cell in the sample is automatically assigned its nearest cluster from of the selected controls for a more accurate AF subtraction.</li>
<li>Inspect the AutoSpectral AF results against standard unmixing. Negative spread and other artifacts caused by inhomogeneous autofluorescence should be much improved.</li>
</ol>
<p>Documentation:</p>
<ul>
<li><a href="https://www.colibri-cytometry.com/post/introducing-autospectral-an-optimized-unmixing-workflow">AutoSpectral on the Colibri Cytometry blog</a></li>
<li><a href="https://www.colibri-cytometry.com/post/autospectral-single-cell-autofluorescence">AutoSpectral AF on the Colibri Cytometry blog</a></li>
<li><a href="https://github.com/DrCytometer/AutoSpectral">AutoSpectral package on Github</a></li>
</ul>
'''

autospectral_cleaning_help_text = '''
<h3>AutoSpectral Control Cleaning — Workflow Guide</h3>
<p><b>Important:</b> AutoSpectral Control Cleaning is designed for <b>spectral flow cytometry</b> single-stained cell controls. It will have less impact on bead controls and has not been tested on conventional flow samples.</p>
<p><b>Note on unstained samples:</b> If you intend to use <b>AutoSpectral AF</b>, do <em>not</em> add unstained samples to the Spectral Process table. Unstained samples should only be used as the negative reference (assigned via the "Unstained Negative" column), not as spectral controls in their own right. Including them as controls will produce manual AF extraction profiles and can be used as an alternative to AutoSpectral AF.</p>
<h4>Workflow</h4>
<ol>
<li><b>Assign unstained negatives:</b> Ensure each cell control has an "Unstained Negative" assigned in the table. Right-click a sample in the Sample panel and select "Mark as Unstained" to make it available as a negative reference.</li>
<li><b>Tick "Exclude noise" if needed:</b> For controls where intrusive autofluorescence is expected (e.g. tissue-derived or highly autofluorescent cell types), tick the "Exclude noise" checkbox for that control <em>before</em> running Clean Controls. This step must be done first — it cannot be applied retrospectively without re-running the pipeline.</li>
<li><b>Run "Clean Controls":</b> Click the "Clean Controls" button. The pipeline will run for all eligible cell controls (those with an unstained negative assigned). Steps performed per control:
  <ul>
    <li>Saturation exclusion — removes detector-saturated events.</li>
    <li>Scatter matching — selects negative events whose scatter profile matches the positive control, reducing background due to cell size/granularity differences.</li>
    <li>Noise exclusion (if ticked) — identifies and removes intrusive autofluorescent events from the positive control using PCA on the matched unstained.</li>
  </ul>
</li>
<li><b>Inspect diagnostic plots:</b> After cleaning, use the scatter-matching and noise exclusion diagnostic plots (visible below when cleaning is active) to verify that the cleaning has worked as expected.</li>
<li><b>Use Cleaned profiles:</b> Once cleaning is complete, each eligible control will show a "Use Cleaned" checkbox. This is ticked by default. Cleaned controls use robust linear model (RLM) profile extraction for improved accuracy. Uncheck to revert to the standard gate-mean method for a specific control.</li>
<li><b>Recalculate:</b> The spectral model is automatically recalculated after cleaning. If you change any settings, click "Recalculate" to update.</li>
</ol>
<p>Documentation: <a href="https://drcytometer.github.io/AutoSpectral/articles/09_Cleaning.html">AutoSpectral package on Github</a></p>
'''