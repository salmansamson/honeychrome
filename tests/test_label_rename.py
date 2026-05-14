# test_label_rename.py
import pytest
from honeychrome.controller_components.gml_functions_mod_from_flowkit import _rename_channel_in_gml

# Minimal but realistic GML containing PE alongside PE-Cy7 and PE-CF594.
# The fcs-dimension name attributes are what get renamed; gate names and
# parent_id attributes should be untouched.
SAMPLE_GML = """\
<gating:Gating-ML
    xmlns:gating="http://www.isac-net.org/std/Gating-ML/v2.0/gating"
    xmlns:data-type="http://www.isac-net.org/std/Gating-ML/v2.0/datatypes"
    xmlns:transforms="http://www.isac-net.org/std/Gating-ML/v2.0/transformations">
  <transforms:logicle transforms:id="PE">
    <transforms:transformation_parameter transforms:value="262144"/>
  </transforms:logicle>
  <transforms:logicle transforms:id="PE-Cy7">
    <transforms:transformation_parameter transforms:value="262144"/>
  </transforms:logicle>
  <gating:RectangleGate gating:id="PE gate" gating:parent_id="root">
    <data-type:dimension gating:min="0.1" gating:max="0.9">
      <data-type:fcs-dimension data-type:name="PE"/>
    </data-type:dimension>
  </gating:RectangleGate>
  <gating:RectangleGate gating:id="PE-Cy7 gate" gating:parent_id="root">
    <data-type:dimension gating:min="0.1" gating:max="0.9">
      <data-type:fcs-dimension data-type:name="PE-Cy7"/>
    </data-type:dimension>
  </gating:RectangleGate>
</gating:Gating-ML>
"""

def test_rename_does_not_corrupt_siblings():
    """Renaming PE must not touch PE-Cy7 anywhere in the GML."""
    result = _rename_channel_in_gml(SAMPLE_GML, "PE", "mCherry")
    assert 'data-type:name="mCherry"' in result or 'name="mCherry"' in result
    assert "PE-Cy7" in result          # sibling survives intact
    assert ">PE<" not in result        # old name gone from element text (sanity)
    # The fcs-dimension for PE-Cy7 must still say PE-Cy7, not mCherry-Cy7
    assert 'name="PE-Cy7"' in result or 'data-type:name="PE-Cy7"' in result

def test_rename_updates_transform_id():
    """The transforms element id for PE should also be renamed."""
    result = _rename_channel_in_gml(SAMPLE_GML, "PE", "mCherry")
    assert 'transforms:id="mCherry"' in result or 'id="mCherry"' in result
    assert 'transforms:id="PE-Cy7"' in result or 'id="PE-Cy7"' in result  # sibling intact

def test_rename_absent_name_is_noop():
    """Renaming a channel not present in the GML returns the string unchanged."""
    result = _rename_channel_in_gml(SAMPLE_GML, "BV421", "BV421-renamed")
    assert result == SAMPLE_GML

def test_rename_idempotent():
    """Applying the same rename twice is safe."""
    once  = _rename_channel_in_gml(SAMPLE_GML, "PE", "mCherry")
    twice = _rename_channel_in_gml(once, "PE", "mCherry")
    assert once == twice