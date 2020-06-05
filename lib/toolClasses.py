import arcpy
import numpy as np
import datetime
import sys
import importlib

import setup
import parameterValidation as pv
import t1_demConditioning as t1
import t2a_preparePrecipData as t2a
import t2b_calculateCN as t2b
import t2c_identifyIDAs as t2c
import t3_demRecondition as t3
import t4_spi as t4
import t5a_kfact as t5a
import t5b_cfact as t5b
import t5c_usle as t5c
import t6_evi as t6

importlib.reload(setup)
importlib.reload(pv)
importlib.reload(t1)
importlib.reload(t2a)
importlib.reload(t2b)
importlib.reload(t2c)
importlib.reload(t3)
importlib.reload(t4)
importlib.reload(t5a)
importlib.reload(t5b)
importlib.reload(t5c)
importlib.reload(t6)

wd = sys.path[0]

class conditionTheLidarDem(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "1. Condition the LiDAR DEM"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Culverts",
            name="culverts",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Polyline"]

        param1 = arcpy.Parameter(
            displayName="Watershed area (unbuffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ["Polygon"]

        param2 = arcpy.Parameter(
            displayName="Raw LiDAR DEM (vertical units in meters)",
            name="raw_lidar_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Buffer size in meters",
            name="buffer_size",
            datatype="Long",
            parameterType="Optional",
            direction="Input")
        param3.value = 100

        param4 = arcpy.Parameter(
            displayName="Output conditioned DEM",
            name="output_conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param5 = arcpy.Parameter(
            displayName="Output optimized fill",
            name="output_optimized_fill",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        pv.checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        culverts = parameters[0].valueAsText
        watershedFile = parameters[1].valueAsText
        lidarRaw = parameters[2].valueAsText
        bufferSize = parameters[3].value
        demCondFile = parameters[4].valueAsText
        demOptimFillFile = parameters[5].valueAsText
        
        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t1.demConditioning(
            culverts,
            watershedFile,
            lidarRaw,
            bufferSize,
            demCondFile,
            demOptimFillFile,
            ws
        )

class downloadPrecipitationData(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2a. Download precipitation data"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
        displayName= "Download frequency-duration data? If yes, define frequency and duration below.",
        name="download_frequency_duration",
        datatype="Boolean",
        parameterType="Required",
        direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Frequency (years)",
            name="frequency",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.value = '10'
        param1.filter.type = "ValueList"
        param1.filter.list = [1, 2, 5, 10, 25, 50, 100, 200, 500, 1000]

        param2 = arcpy.Parameter(
            displayName="Duration (hours)",
            name="duration",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = [2, 3, 6, 12, 24]
        param2.value = '24'

        param3 = arcpy.Parameter(
            displayName="Locally stored frequency-duration data (zip file)",
            name="local_frequency_duration",
            datatype="File",
            parameterType="Optional",
            direction="Input")
        param3.filter.list = ["zip"]

        param4 = arcpy.Parameter(
            displayName="Conditioned DEM (for template)",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="Output precipitation frequency-duration raster",
            name="output_precipitation_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        downloadBool = parameters[0].valueAsText
        frequency = parameters[1].valueAsText
        duration = parameters[2].valueAsText
        localCopy = parameters[3].valueAsText
        rasterTemplateFile = parameters[4].valueAsText
        outPrcp = parameters[5].valueAsText
        
        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t2a.preparePrecipData(
            downloadBool,
            frequency,
            duration,
            localCopy,
            rasterTemplateFile,
            outPrcp,
            ws
        )

class createCurveNumberRaster(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2b. Create curve number raster"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Download Cropland Data Layers? If yes, define years below. If no, define locally stored layers",
            name="download_cropland_data_layers",
            datatype="Boolean",
            parameterType="Required",
            direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Start year. Five total years is recommended",
            name="start_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.filter.type = "ValueList"
        param1.filter.list = np.arange(2008,datetime.date.today().year - 1).tolist()
        param1.value = 2009

        param2 = arcpy.Parameter(
            displayName="End year",
            name="end_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = np.arange(2009,datetime.date.today().year).tolist()
        param2.value = datetime.date.today().year - 1

        param3 = arcpy.Parameter(
            displayName="Use locally stored Cropland Data Layers?",
            name="use_locally_stored_cropland_data_layers",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input",
            multiValue=True)
        param3.enabled = 0

        param4 = arcpy.Parameter(
            displayName="gSSURGO geodatabase",
            name="gssurgo_geodatabase",
            datatype="Workspace",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Local Database"]

        param5 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param5.filter.list = ["Polygon"]

        param6 = arcpy.Parameter(
            displayName="Conditioned DEM for raster template",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Output curve number raster (high estimate)",
            name="output_curve_number_high",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param8 = arcpy.Parameter(
            displayName="Output curve number raster (low estimate)",
            name="output_curve_number_low",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        pv.checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        downloadBool = parameters[0].valueAsText
        yrStart = parameters[1].valueAsText
        yrEnd = parameters[2].valueAsText
        localCdlList = parameters[3].valueAsText
        gSSURGO = parameters[4].valueAsText
        watershedFile = parameters[5].valueAsText
        demFile = parameters[6].valueAsText
        outCnHigh = parameters[7].valueAsText
        outCnLow = parameters[8].valueAsText
        
        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t2b.calculateCN(
            downloadBool,
            yrStart,
            yrEnd,
            localCdlList,
            gSSURGO,
            watershedFile,
            demFile,
            outCnLow,
            outCnHigh,
            ws
        )

class internallyDrainingAreas(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2c. Identify internally draining areas"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Optimized fill raster",
            name="optimized_fill_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Precipitation frequency-duration raster",
            name="precipitation_frequency_duration_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Curve number raster",
            name="curve_number_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Polygon"]

        param5 = arcpy.Parameter(
            displayName="Output internally draining areas",
            name="internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param6 = arcpy.Parameter(
            displayName="Output DEM excluding internally draining areas",
            name="dem_excluding_internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        pv.checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        optimFillFile = parameters[1].valueAsText
        prcpFile = parameters[2].valueAsText
        cnFile = parameters[3].valueAsText
        watershedFile = parameters[4].valueAsText
        nonContributingAreasFile = parameters[5].valueAsText
        demFinalFile = parameters[6].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t2c.identifyIDAs(
            demFile,
            optimFillFile,
            prcpFile,
            cnFile,
            watershedFile,
            nonContributingAreasFile,
            demFinalFile,
            ws
        )

class demReconditioning(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "3. Recondition DEM for internally draining areas"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="DEM excluding internally draining areas",
            name="dem_excluding_internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Internally draining areas raster",
            name="internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName='Best management practice areas (i.e., grass waterways, riparian buffer areas)',
            name="additional_non_contributing_areas",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Output Reconditioned DEM excluding internally draining areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        nonContributingAreasFile = parameters[1].valueAsText
        grassWaterwaysFile = parameters[2].valueAsText
        outFile = parameters[3].valueAsText
        
        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t3.demRecondition(
            demFile,
            nonContributingAreasFile,
            grassWaterwaysFile,
            outFile,
            ws
        )

class calculateStreamPowerIndex(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "4. Calculate Stream Power Index"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Reconditioned DEM excluding non-contributing areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName='Flow accumulation threshold (for a 3-meter resolution grid)',
            name="flow_accumulation_threshold",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param2.value = '50000'

        param3 = arcpy.Parameter(
            displayName="Output stream power index raster",
            name="stream_power_index_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        fillFile = parameters[1].valueAsText
        facThreshold = int(parameters[2].valueAsText)
        outFile = parameters[3].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t4.spi(demFile, fillFile, facThreshold, outFile)

class rasterizeKfactorForUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5a. Rasterize K-factor for USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="gSSURGO database",
            name="gssurgo_geodatabase",
            datatype="Workspace",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Local Database"]

        param1 = arcpy.Parameter(
            displayName="K-factor field",
            name="k_factor_field",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param1.value = 'kwfact'

        param2 = arcpy.Parameter(
            displayName='Conditioned DEM (raster grid template)',
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param3.filter.list = ["Polygon"]

        param4 = arcpy.Parameter(
            displayName="Output K-factor raster",
            name="k_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        gssurgoGdb = parameters[0].valueAsText
        attField = parameters[1].valueAsText
        demFile = parameters[2].valueAsText
        watershedFile = parameters[3].valueAsText
        outRaster = parameters[4].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t5a.kfact(
            gssurgoGdb,
            attField,
            demFile,
            watershedFile,
            outRaster,
            ws
        )

class rasterizeCfactorForUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5b. Rasterize C-factor for USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Download Cropland Data Layers? If yes, define years below. If no, define locally stored layers",
            name="download_cropland_data_layers",
            datatype="Boolean",
            parameterType="Required",
            direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Start year. Five total years is recommended",
            name="start_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.filter.type = "ValueList"
        param1.filter.list = np.arange(2008,datetime.date.today().year - 1).tolist()
        param1.value = 2009

        param2 = arcpy.Parameter(
            displayName="End year",
            name="end_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = np.arange(2009,datetime.date.today().year).tolist()
        param2.value = datetime.date.today().year - 1

        param3 = arcpy.Parameter(
            displayName="Use locally stored Cropland Data Layers?",
            name="use_locally_stored_cropland_data_layers",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input",
            multiValue=True)
        param3.enabled = 0

        param4 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Polygon"]

        param5 = arcpy.Parameter(
            displayName="Conditioned DEM, for template",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Output crop rotation raster",
            name="crop_rotation_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")
        param6.symbology = sys.path[0] + '/etc/rotationSymbology.lyr'

        param7 = arcpy.Parameter(
            displayName="Output C-factor raster (high estimate)",
            name="output_c_factor_high",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param8 = arcpy.Parameter(
            displayName="Output C-factor raster (low estimate)",
            name="output_c_factor_low",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        pv.checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        downloadBool = parameters[0].valueAsText
        yrStart = parameters[1].valueAsText
        yrEnd = parameters[2].valueAsText
        localCdlList = parameters[3].valueAsText
        watershedFile = parameters[4].valueAsText
        rasterTemplateFile = parameters[5].valueAsText
        outRotation = parameters[6].valueAsText
        outHigh = parameters[7].valueAsText
        outLow = parameters[8].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t5b.cfact(
            downloadBool,
            localCdlList,
            watershedFile,
            rasterTemplateFile,
            yrStart,
            yrEnd,
            outRotation,
            outHigh,
            outLow,
            ws
        )

class calculateSoilLossUsingUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5c. Calculate soil loss index using USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Reconditioned DEM excluding non-contributing areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Erosivity raster (SI units)",
            name="erosivity_raster",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Erosivity constant",
            name="erosivity_constant",
            datatype="String",
            parameterType="Optional",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="K-factor raster",
            name="k_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="C-factor raster",
            name="c_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Flow Accumulation threshold (for a 10-meter resolution grid)",
            name="flow_accumulation_threshold",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param6.value = '1000'

        param7 = arcpy.Parameter(
            displayName="Output soil loss raster",
            name="soil_loss_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if parameters[2].value is not None:
            parameters[3].enabled = 0
        elif parameters[3].value is not None:
            parameters[2].enabled = 0
        else:
            parameters[2].enabled = 1
            parameters[3].enabled = 1
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        demFile = parameters[0].valueAsText
        fillFile = parameters[1].valueAsText
        erosivityFile = parameters[2].valueAsText
        erosivityConstant = parameters[3].valueAsText
        kFactorFile = parameters[4].valueAsText
        cFactorFile = parameters[5].valueAsText
        facThreshold = int(parameters[6].valueAsText)
        outFile = parameters[7].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])
        t5c.usle(
            demFile,
            fillFile,
            erosivityFile,
            erosivityConstant,
            kFactorFile,
            cFactorFile,
            facThreshold,
            outFile,
            ws
        )

class erosionScore(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "6. Calculate erosion vulnerability index"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Soil loss raster",
            name="soil_loss_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Stream power index raster",
            name="stream_power_index_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Only calculate for agricultural land uses as identified by crop rotation raster?",
            name="ag_subset_bool",
            datatype="Boolean",
            parameterType="Required",
            direction="Input")
        param2.value = 0

        param3 = arcpy.Parameter(
            displayName="Crop rotation raster",
            name="rotation",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Zonal statistic boundary feature class",
            name="zonal_boundary",
            datatype="Feature Layer",
            parameterType="Optional",
            direction="Input")
        param4.filter.list = ["Polygon"]

        param5 = arcpy.Parameter(
            displayName="Zonal statistic field",
            name="zonal_statistic_field",
            datatype="Field",
            parameterType="Optional",
            direction="Input")
        param5.parameterDependencies = [param4.name]

        param6 = arcpy.Parameter(
            displayName="Only calculate within zonal boundaries?",
            name="zonal_subset_bool",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Output erosion vulnerability index raster",
            name="erosion_score_raster",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Output")

        param8 = arcpy.Parameter(
            displayName="Output summary table",
            name="output_summary_table",
            datatype="Table",
            parameterType="Optional",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        # parameters = [param0]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[2].value == 0:
            parameters[3].enabled = 0
            parameters[3].parameterType = "Optional"
        else:
            parameters[3].enabled = 1
            parameters[3].parameterType = "Required"

        if parameters[4].value is not None:
            parameters[5].enabled = 1
            parameters[5].parameterType = "Required"
            parameters[6].enabled = 1
            parameters[6].parameterType = "Required"
            parameters[6].value = 1
            parameters[8].enabled = 1
            parameters[8].parameterType = "Required"
        else:
            parameters[5].enabled = 0
            parameters[5].parameterType = "Optional"
            parameters[6].enabled = 0
            parameters[6].parameterType = "Optional"
            parameters[6].value = 0
            parameters[8].enabled = 0
            parameters[8].parameterType = "Optional"
        pv.replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        pv.checkForSpaces(parameters)
        pv.checkProjectionsOfInputs(parameters)
        pv.checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        #Inputs
        usle_file = parameters[0].valueAsText
        spi_file = parameters[1].valueAsText
        subset_ag = parameters[2].valueAsText
        ag_file = parameters[3].valueAsText
        zonal_file = parameters[4].valueAsText
        zonal_id = parameters[5].valueAsText
        subset_zone = parameters[6].valueAsText
        out_raster = parameters[7].valueAsText
        out_tbl = parameters[8].valueAsText

        ws = setup.setupWorkspace(wd)
        setup.setupTemp(ws['tempDir'], ws['tempGdb'])

        t6.evi(usle_file, spi_file, subset_ag, ag_file, zonal_file, zonal_id, subset_zone, out_raster, out_tbl, ws)
