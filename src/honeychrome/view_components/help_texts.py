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
An alternative negative is the <i>Unstained Negative</i>. I.e. the profile is defined as the mean fluorescence of the positively gated sample, 
minus the fluorescence of the negatively gated <i>unstained</i> sample. "Pos Unstained" and "Neg Unstained" gates are added to the raw gating if you didn't already create them.
</li>

<li>
If any singly stained spectral control is missing, you may load it from previous experiments (if an exact match is available). 
Select <i>control type</i> as "Single Stained Control from Library", and enter the label name. 
Exact matches from previously processed data will be returned under <i>sample name</i>.
</li>
</ol>

<h4>Profiles Viewer, Similarity Matrix, Unmixing Matrix</h4>
<p>
The spectral profiles are displayed in the profiles viewer; the similarity matrix and unmixing matrix are also calculated and displayed. 
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



<h4>Further Reading</h4>

<p>
For background on spectral unmixing processes and algorithms, see <a href="https://onlinelibrary.wiley.com/doi/full/10.1002/cyto.a.22272">Novo, Gregori and Rajwa 2013</a>.
</p>
<p>
Also highly recommended is Oliver Burton's Colibri Cytometry blog, e.g. <a href="https://www.colibri-cytometry.com/post/what-s-an-unmixing-matrix">What's an Unmixing Matrix?</a>.
</p>
'''

nxn_help_text = '''
<ul>
<li>If your panel is large, select one or more rows in the editor above, so that the corresponding rows of the NxN array are plotted below. This makes the plots easier to find, quicker to plot, and quicker to fine-tune.</li>
<li>If no labels are selected above, the full array of NxN plots will be calculated. <b>Warning: this is slow if N is large!</b> If you are using a 60-colour panel, that means calculating 1800 2D histograms at once.</li>
<li>Roll scroll wheel to adjust spillover (fine tuning) (row label spills into column labels)</li>
<li>Hover to inspect spillover of each cell in the array</li>
</ul>
'''