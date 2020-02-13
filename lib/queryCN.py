import numpy as np

def queryCN(lc, hsg, scen, coverTypeLookup, cnLookup):
    cts = np.array(coverTypeLookup[lc][scen])
    hsg = list(map(str, hsg))
    if len(cts) == 0:
        return None
    if scen == 'high':
        hydCond = 'Poor'
    else:
        hydCond = 'Good'
    coverBool = np.in1d(cnLookup['COVER_CODE'], cts)
    scenBool = np.in1d(cnLookup['HYDROLOGIC_CONDITION'], np.array([hydCond, ''], dtype="|S25"))
    for ct in cts:
        ctBool = cnLookup['COVER_CODE'] == ct
        boolMat = np.vstack((coverBool,scenBool,ctBool))
        cns = cnLookup[hsg][boolMat.all(axis=0)]
        cns = cns.view('i1').reshape(len(cns),len(hsg))
        acrossHgs = np.mean(cns, axis=1)
        if hydCond == 'Good':
            cn = np.min(acrossHgs)
        else:
            cn = np.max(acrossHgs)
    return cn
