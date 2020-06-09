import numpy as np

def queryCN(lc, hsgs, scen, coverTypeLookup, cnLookup):
    cts = np.array(coverTypeLookup[lc][scen])
    hsgs = list(map(str, hsgs))
    if len(cts) == 0:
        return None
    if scen == 'high':
        hydCond = 'Poor'
    else:
        hydCond = 'Good'
    scenBool = np.in1d(cnLookup['HYDROLOGIC_CONDITION'], np.array([hydCond, ''], dtype="|S25"))
    cns = np.zeros((cnLookup.shape[0], len(hsgs)))
    for i, hsg in enumerate(hsgs):
        cns[:, i] = cnLookup[hsg]
    for ct in cts:
        ctBool = cnLookup['COVER_CODE'] == ct
        boolMat = ctBool * scenBool
        cns_ct = cns[boolMat]
        acrossHsgs = np.mean(cns_ct, axis=1)
        if hydCond == 'Good':
            cn = np.min(acrossHsgs)
        else:
            cn = np.max(acrossHsgs)
    return cn
