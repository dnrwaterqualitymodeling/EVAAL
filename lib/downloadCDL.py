import arcpy
import numpy as np
import subprocess as sp
import requests
import xml

def downloadCDL(yrStart, yrEnd, tempDir, watershedCdlPrj, rid):
    years = np.arange(int(yrStart), int(yrEnd) + 1).tolist()
    cdlUrl = r'http://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile?'
    ext = arcpy.Describe(watershedCdlPrj).extent
    ping = sp.call(['ping', '-n', '1', 'nassgeodata.gmu.edu'])
    if ping == 1:
        arcpy.AddError('The CropScape server is down. Please try again later, or download local \
            Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
    cdlTiffs_fl = []
    for year in years:
        year = str(year)
        clipUrl = cdlUrl\
            + r'year='\
            + year + r'&'\
            + r'bbox='\
            + str(ext.XMin) + ','\
            + str(ext.YMin) + ','\
            + str(ext.XMax) + ','\
            + str(ext.YMax)
        try:
            downloadLocXml = tempDir + '/download_' + year + '_' + rid + '.xml'
            r = requests.get(clipUrl, allow_redirects=True)
            open(downloadLocXml, 'wb').write(r.content)
            # urllib.urlretrieve(clipUrl, downloadLocXml)
            tiffUrl = xml.etree.ElementTree.parse(downloadLocXml).getroot()[0].text
            downloadTiff = tempDir + '/cdl_' + year + '_' + rid + '.tif'
            r = requests.get(tiffUrl, allow_redirects=True)
            open(downloadTiff, 'wb').write(r.content)
            # urllib.urlretrieve(tiffUrl, downloadTiff)
        except:
            arcpy.AddError('The CropScape server is down. Please try again later, or download local \
                Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
        cdlTiffs_fl.append(downloadTiff)

    # For clipping to watershed extent
    cdlTiffs = []
    for i,fullCdl in enumerate(cdlTiffs_fl):
            clipCdl = tempDir + '/cdl_' + str(i) + '_' + rid + '.tif'
                    #testing the ClippingGeometry option..
            arcpy.Clip_management(fullCdl, '', clipCdl, watershedCdlPrj, '#', 'ClippingGeometry')
            cdlTiffs.append(clipCdl)
    return cdlTiffs
