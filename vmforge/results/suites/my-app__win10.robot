*** Settings ***
Library    vmforge.framework.robot.keywords.VmForgeKeywords    platform=vsphere    executor=powershell
Suite Setup       Clone VM    win10-tpl    automation
Suite Teardown    Teardown VM

*** Test Cases ***
my-app :: win10 :: t1
    [Tags]    REG1    my-app
    [Setup]    Revert Snapshot    automation
    ${output}=    Execute PS    Get-Item C:/foo
    Check Field    ${output}    result.code    0
