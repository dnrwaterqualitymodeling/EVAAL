import arcpy
import numpy as np
from packaging.version import Version


def aggregateSSURGO(table_name, att_field, elem_field, wt_field, stat):
    nRows = int(arcpy.GetCount_management(table_name).getOutput(0))
    elem = np.empty(nRows, dtype='S15')
    if Version(np.version.version) < Version('1.20'):
      att = np.empty(nRows, dtype=np.float)
      wt = np.empty(nRows, dtype=np.float)
    else:
      att = np.empty(nRows, dtype=float)
      wt = np.empty(nRows, dtype=float)
    rows = arcpy.da.SearchCursor(table_name, [elem_field, att_field, wt_field])
    for i, row in enumerate(rows):
        elem[i] = row[0]
        att[i] = row[1]
        wt[i] = row[2]
    del i, row, rows
    # Delete rows with nan values
    inds = np.invert((np.isnan(att) + np.isnan(wt)) > 0)
    elem = elem[inds]
    att = att[inds]
    wt = wt[inds]
    # If weighted average, exclude weights equal to zero, if top, anything below the first layer
    if stat == 'wa':
        inds = np.invert(wt == 0)
    elif stat == 'top':
        inds = np.invert(wt > 0)
    elem = elem[inds]
    att = att[inds]
    wt = wt[inds]
    if Version(np.version.version) < Version('1.20'):
      attAve = np.zeros([len(np.unique(elem)),2], dtype=np.float)
    else:
      attAve = np.zeros([len(np.unique(elem)),2], dtype=float)
    for i,m in enumerate(np.unique(elem)):
        ind = np.where(elem == m)
        if stat == 'wa':
            attAve[i,0:2] = np.array(np.average(att[ind], weights=wt[ind], returned=True))
        elif stat == 'top':
            attAve[i,0:2] = np.array(np.average(att[ind], returned=True))
    del i,m
    attAve = attAve[np.where(attAve[:,1] > 0)]
    elem = np.array(np.unique(elem)[np.where(attAve[:,1] > 0)])
    return {'element' : elem, 'attAve' : attAve}
