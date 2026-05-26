*** Settings ***
Documentation       Test suite for SSH-based VM management via SSHVMManager.
...
...                 Target: Windows 10 64bit at 10.40.164.105 (SSH port 22).
...                 Covers:
...                 - Command execution (exit code, stdout, stderr)
...                 - Result structure validation (exit_code, stdout, stderr, pid)
...
...                 Prerequisites:
...                 - SSH service running on the target VM
...                 - Variables VM_HOST, VM_USER, VM_PASS can be overridden
...                   via --variable on the command line.

Library             SshVmLibrary.py

Suite Setup         Connect To VM Via SSH    ${VM_HOST}    ${VM_USER}    ${VM_PASS}
Suite Teardown      Disconnect From VM SSH


*** Variables ***
${VM_HOST}      10.40.164.87
${VM_USER}      admin
${VM_PASS}      admin
${VM_PORT}      22


*** Test Cases ***

# =========================================================================
# Result structure
# =========================================================================

TC-01 Execute Command Returns Expected Result Keys
    [Documentation]    The result dict must always contain exit_code, stdout, stderr, pid.
    [Tags]    smoke

    Execute SSH Command    hostname

    Result Should Have Key    exit_code
    Result Should Have Key    stdout
    Result Should Have Key    stderr
    Result Should Have Key    pid


# =========================================================================
# Command execution
# =========================================================================

TC-02 Hostname Command Returns Machine Name
    [Documentation]    hostname should exit 0 and produce non-empty stdout.
    [Tags]    windows    positive

    Execute SSH Command    hostname

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-03 Echo Command Succeeds With Exit Code Zero
    [Documentation]    echo via cmd.exe should exit 0.
    [Tags]    windows    positive

    Execute SSH Command    echo hello ssh vsphere

    Exit Code Should Be    0
    Stdout Should Contain  hello ssh vsphere


TC-04 Whoami Returns A Username
    [Documentation]    whoami should exit 0 and return the current user.
    [Tags]    windows    positive

    Execute SSH Command    whoami

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-05 Ipconfig Shows Network Configuration
    [Documentation]    ipconfig should exit 0 and list network adapters in stdout.
    [Tags]    windows    positive

    Execute SSH Command    ipconfig

    Exit Code Should Be       0
    Stdout Should Not Be Empty
    Stdout Should Contain     IPv4


TC-06 Dir Command Lists Files
    [Documentation]    dir C:\\ should list files in the root drive.
    [Tags]    windows    positive

    Execute SSH Command    dir C:\\

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-07 Tasklist Returns Running Processes
    [Documentation]    tasklist should exit 0 and populate stdout with process info.
    [Tags]    windows    positive

    Execute SSH Command    tasklist

    Exit Code Should Be       0
    Stdout Should Not Be Empty


TC-08 Systeminfo Returns System Details
    [Documentation]    systeminfo should exit 0 and return OS details including hostname.
    [Tags]    windows    positive

    ${result}=    Execute SSH Command    systeminfo

    Exit Code Should Be       0
    Stdout Should Not Be Empty
    Stdout Should Contain     Host Name


TC-09 Multi-Command Pipeline Returns Combined Output
    [Documentation]    Command chaining with & should work and exit 0.
    [Tags]    windows    positive

    Execute SSH Command    echo first & echo second

    Exit Code Should Be    0
    Stdout Should Contain  first


# =========================================================================
# Failure scenarios
# =========================================================================

TC-10 Command That Does Not Exist Returns Non-Zero Exit Code
    [Documentation]    Running a non-existent executable should yield a non-zero exit code.
    [Tags]    windows    negative

    Execute SSH Command    this_command_does_not_exist_xyz_123

    Exit Code Should Not Be Zero
