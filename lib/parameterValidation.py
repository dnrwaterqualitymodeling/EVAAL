import arcpy


def checkForSpaces(parameters):
    for p in parameters:
        if p.value:
            if p.direction == 'Input' and p.datatype in ['Feature Layer','Raster Layer','Table']:
                # Value of paramater can only be string type. Doesn't work for multivalue
                if not p.multiValue:
                    path = arcpy.Describe(p.value).catalogPath
                    if ' ' in path:
                        p.setErrorMessage("Spaces are not allowed in dataset path.")


def replaceSpacesWithUnderscores(parameters):
    for p in parameters:
        if p.value:
            if p.direction == 'Output' and p.datatype in ['Feature Layer','Raster Layer','Table']:
                if ' ' in p.value.value:
                    p.value = p.value.value.replace(' ', '_')
                    p.setWarningMessage('Spaces in file path were replaced with underscores.')


def checkProjectionsOfInputs(parameters):
    for p in parameters:
        if p.value:
            if p.direction == 'Input' and p.datatype in ['Feature Layer','Raster Layer']:
                # Value of paramater can only be string type. Doesn't work for multivalue
                if not p.multiValue:
                    cs = arcpy.Describe(p.value).spatialReference.name
                    if cs not in ['NAD_1983_HARN_Transverse_Mercator', 'NAD_1983_HARN_Wisconsin_TM']:
                        p.setErrorMessage('Dataset must be projected in \
                            NAD_1983_HARN_Transverse_Mercator coordinate system.')


def checkDupOutput(parameters):
    output_names = []
    for p in parameters:
        if p.value:
            if p.direction == 'Output':
                output_names.append(p.value.value)
    if len(output_names) != len(set(output_names)):
        p.setErrorMessage('Duplicate output names are not allowed')
