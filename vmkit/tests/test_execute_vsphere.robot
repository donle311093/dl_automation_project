*** Settings ***
Documentation       Test suite for vSphere guest command execution via VMware Tools.
...
...                 Workflow:
...                 1. Clone template VM "${TEMPLATE_NAME}" from folder "${TEMPLATE_FOLDER}"
...                    to folder "${TARGET_FOLDER}" as "${TEMPLATE_NAME}_automation_test".
...                 2. Run all execution tests against the cloned VM.
...                 3. Delete the cloned VM on teardown.
...
...                 Covers:
...                 - Result structure validation (pid, exit_code, stdout, stderr)
...                 - PowerShell command execution (echo, hostname, Get-Process, Get-Date)
...                 - Failure scenarios: invalid command with non-zero exit code
...
...                 Prerequisites:
...                 - vCenter reachable at the host defined in vsphere/.config
...                 - VMware Tools running inside the target VM
...                 - Variables TEMPLATE_FOLDER, TEMPLATE_NAME, TARGET_FOLDER,
...                   WIN_USER, WIN_PASS can be overridden via --variable on the
...                   command line.

Library             VsphereExecuteLibrary.py

Suite Setup         Run Keywords
...                     Connect To VCenter                                                        AND
...                     Find VM In Folder    ${TEMPLATE_FOLDER}    ${TEMPLATE_NAME}                AND
...                     Clone VM To Folder   ${TARGET_FOLDER}      ${TEMPLATE_NAME}_automation_test    ${SNAPSHOT_NAME}    AND
...                     Login To VM          ${WIN_USER}           ${WIN_PASS}
Suite Teardown      Run Keywords
...                     Delete VM In Folder    ${TARGET_FOLDER}    ${TEMPLATE_NAME}_automation_test    AND
...                     Disconnect From VCenter


*** Variables ***
${TEMPLATE_FOLDER}  VM_Template
${TEMPLATE_NAME}    windows-11-64
${TARGET_FOLDER}    Lab
${SNAPSHOT_NAME}    Init
${WIN_USER}         admin
${WIN_PASS}         admin


*** Test Cases ***

# =========================================================================
# Result Structure
# =========================================================================

TC-01 Execute Command Returns Expected Result Keys
    [Documentation]    The result dict must always contain pid, exit_code,
    ...                stdout, and stderr.
    [Tags]    smoke

    Execute Command On VM    Write-Output hello

    Result Should Have Key    pid
    Result Should Have Key    exit_code
    Result Should Have Key    stdout
    Result Should Have Key    stderr


TC-02 Execute Command Returns A Valid PID
    [Documentation]    The PID returned by StartProgramInGuest must be a
    ...                positive integer.
    [Tags]    smoke

    ${result}=    Execute Command On VM    Write-Output pid-check

    Should Be True    ${result}[pid] > 0
    ...    msg=Expected a positive PID, got ${result}[pid]


# =========================================================================
# Windows guest — success scenarios
# =========================================================================

TC-03 Echo Command Succeeds With Exit Code Zero
    [Documentation]    Write-Output on a Windows guest must exit with code 0.
    [Tags]    windows    positive

    Execute Command On VM    Write-Output hello vsphere

    Exit Code Should Be    0


TC-04 Hostname Command Returns Machine Name In Stdout
    [Documentation]    $env:COMPUTERNAME should output the machine name.
    [Tags]    windows    positive

    Execute Command On VM    Write-Output $env:COMPUTERNAME

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-05 Get-Process Command Returns Process List
    [Documentation]    Get-Process via PowerShell should exit 0 and populate stdout.
    [Tags]    windows    positive

    Execute Command On VM    Get-Process

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-06 Get-Date Command Returns Current Date
    [Documentation]    Get-Date should return a non-empty date string.
    [Tags]    windows    positive

    Execute Command On VM    Get-Date -Format "yyyy-MM-dd"

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-07 Stderr Is Empty For A Clean Command
    [Documentation]    A clean PowerShell command should produce no stderr output.
    [Tags]    windows    positive

    Execute Command On VM    Write-Output clean

    Exit Code Should Be    0
    Stderr Should Be Empty


TC-08 Command Without Output Capture Still Returns Exit Code
    [Documentation]    When capture_output=False the function should still
    ...                return the exit code correctly.
    [Tags]    windows    positive

    Execute Command On VM    Write-Output no-capture    capture_output=False

    Exit Code Should Be    0


# =========================================================================
# Windows guest — failure scenarios
# =========================================================================

TC-11 Non-Zero Exit Code On Failing Command
    [Documentation]    Accessing a non-existent path with -ErrorAction Stop
    ...                should yield a non-zero exit code.
    [Tags]    windows    negative

    Execute Command On VM    Get-Item C:\\NonExistentPath_XYZ_12345 -ErrorAction Stop

    Exit Code Should Not Be Zero
