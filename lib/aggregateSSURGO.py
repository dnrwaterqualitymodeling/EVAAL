import arcpy
import numpy as np

def aggregateSSURGO(tableName, attField, elemField, wtField, stat):
    nRows = int(arcpy.GetCount_management(tableName).getOutput(0))
    elem = np.empty(nRows, dtype='S15')
    att = np.empty(nRows, dtype=np.float)
    wt = np.empty(nRows, dtype=np.float)
    rows = arcpy.da.SearchCursor(tableName, [elemField,attField,wtField])
    for i,row in enumerate(rows):
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
    attAve = np.zeros([len(np.unique(elem)),2], dtype=np.float)
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
