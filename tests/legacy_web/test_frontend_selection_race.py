"""Execute the real browser function with delayed HTTP responses."""
import shutil
import subprocess
from pathlib import Path
import pytest


def test_delayed_context_does_not_replace_newer_or_unsaved_roles():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute the browser function')
    html = (Path(__file__).parents[2] / 'src/sr_harness/web/static/platform.html').read_text()
    source = html.split('async function loadCommittedContext(context=null){', 1)[1].split('\nasync function hydrateCommittedContext', 1)[0]
    script = r'''
const assert = require('node:assert/strict');
let serverSessionGeneration=1,selectionSaveVersion=0,selectionSavedVersion=0,selectionSaveInFlight=false;
let renderedDataRevision=2,useCommittedContext=true,variableDescriptions={},dataPreviewGroups=[],dataGroupPreview=null,dataPreview={target:'current'};
let configured=0,resolveResponse;
const api=()=>new Promise(resolve=>{resolveResponse=resolve});
const $=()=>({value:''});
const configureDataPreview=()=>{configured++};
const renderWorkflowNextControls=()=>{};
const snapshot=revision=>({revision,columns:['x','new'],data:[],target:'new',features:['x']});
''' + 'async function loadCommittedContext(context=null){' + source + r'''
(async()=>{
 await loadCommittedContext(snapshot(1));assert.equal(dataPreview.target,'current');
 let pending=loadCommittedContext();selectionSaveVersion++;resolveResponse(snapshot(3));await pending;assert.equal(dataPreview.target,'current');
 await loadCommittedContext(snapshot(3));assert.equal(dataPreview.target,'current');
 selectionSavedVersion=selectionSaveVersion;selectionSaveInFlight=true;
 await loadCommittedContext(snapshot(3));assert.equal(dataPreview.target,'current');selectionSaveInFlight=false;
 pending=loadCommittedContext();serverSessionGeneration++;resolveResponse(snapshot(3));await pending;assert.equal(dataPreview.target,'current');
 await loadCommittedContext(snapshot(3));assert.equal(dataPreview.target,'new');assert.equal(configured,1);assert.equal(renderedDataRevision,3);
})().catch(error=>{console.error(error);process.exit(1)});
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
