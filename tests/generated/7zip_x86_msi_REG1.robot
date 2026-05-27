# AUTO-GENERATED — do not edit manually.
# Source: vuln_automation/src/test/resources/TestConfig/7zip_x86_msi.json
# Generator: python cli.py generate-suite --platform windows --tag REG1
# Product : 7zip x86 msi  |  Signature: 3112  |  Tag: REG1

*** Settings ***
Library     ../../src/robot/VsphereKeywords.py
Library     ../../src/robot/CommandKeywords.py
Library     ../../src/robot/AssertionKeywords.py
Suite Setup       Connect To vSphere
Suite Teardown    Disconnect From vSphere


*** Variables ***
# Resolved từ product_info
${WRAPPER_PATH}              C:/Users/Admin/Desktop/wrapper
${WRAPPER_PATH_PS}           C:\\Users\\Admin\\Desktop\\wrapper
${SIGNATURE}                 3112
${PATCH_ID}                  12
${BASE_VERSION}              18.06
${FILE_INSTALLER}            7z1806.msi
${INSTALLERS_PATH}           //10.40.164.66/test/installers/7z_x86
${INSTALLERS_PATH_PS}        \\\\10.40.164.66\\test\\installers\\7z_x86
${LATEST_INSTALLERS_PATH}    //10.40.164.66/test/installers/7z_x86/latest
${ANALOG_PATH}               //10.40.164.66/test/analog_data
${ANALOG_WRAPPER_PATH}       C:/Users/Admin/Desktop/analog_wrapper
${CLIENT_DATA}               7zip_x86.json
${PS_TOOL}                   C:/Users/Admin/Desktop/wrapper/PSTools/PsExec.exe
${ACCEPT_EULA}               -accepteula -s
${LOG_FOLDER}                C:/temp t
${PRODUCT_ARCH}              32-bit


# ===========================================================
# ENV: windows-10-86
# exe_path: C:\Program Files\7-Zip\7zFM.exe
# ===========================================================

*** Test Cases ***

7zip_x86_msi :: windows-10-86 :: GetLatestInstaller_with_analog
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before
    Execute PS    & New-Item -ItemType Directory -Force -Path "${ANALOG_WRAPPER_PATH}"
    Execute PS    & Copy-Item "${ANALOG_PATH}/analog/*" -Destination "${ANALOG_WRAPPER_PATH}/" -Recurse
    Execute PS    & Copy-Item "${ANALOG_PATH}/analog_test.rb" -Destination "${ANALOG_WRAPPER_PATH}/sample_code/" -Recurse
    Execute PS    & Copy-Item "${ANALOG_PATH}/get_latest_installer.rb" -Destination "${ANALOG_WRAPPER_PATH}/sample_code/" -Recurse
    Execute PS    & Copy-Item "${ANALOG_PATH}/Windows/${CLIENT_DATA}" -Destination "${ANALOG_WRAPPER_PATH}/" -Recurse
    # tested_function
    ${output}=    Execute PS    & ruby "${ANALOG_WRAPPER_PATH}/sample_code/analog_test.rb" --get-patch --data-source "${ANALOG_WRAPPER_PATH}" --input-file "${ANALOG_WRAPPER_PATH}/${CLIENT_DATA}"
    # after: check
    Check Field    ${output}    result.patch_id                             12
    Check Field    ${output}    result.signature.background_patching        0
    Check Field    ${output}    result.signature.fresh_installable          1
    Check Field    ${output}    result.signature.support_3rd_party_patch    true
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: download2_without_installed_base
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before
    Execute PS    ${WRAPPER_PATH}/Test_script/Proxy.ps1
    Execute PS    & New-Item -ItemType Directory -Force -Path "${WRAPPER_PATH}/latest"
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --get --path "${WRAPPER_PATH}/latest" --download 2 --architecture ${PRODUCT_ARCH}
    # after: check
    Check Field    ${output}    result.code       0
    Check Field    ${output}    result.patch_id    12
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: download1_with_patch_id
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --get --path "${WRAPPER_PATH}/latest" --download 1 --checksum_db "${WRAPPER_PATH}/ap_checksum.dat " --patch_id ${PATCH_ID} --architecture ${PRODUCT_ARCH}
    # after: check  [NOTE: cross-field check — expected_sha256 phải bằng sha256]
    Check Field          ${output}    result.code              0
    Check Field          ${output}    result.patch_id          12
    Check Fields Equal   ${output}    result.expected_sha256    result.sha256
    # after: cleanup commands
    Execute PS    & Remove-Item "${LATEST_INSTALLERS_PATH}/*.*"
    Execute PS    & Start-Sleep -s 10
    Execute PS    & Copy-Item "${WRAPPER_PATH}/latest/*" -Destination "${LATEST_INSTALLERS_PATH}" -Recurse
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: Install_with_patch_id
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before — (no commands)
    # tested_function — <std_out>: output của command 1 được inject vào command 2
    ${std_out}=    Execute PS    (Get-ChildItem -Path "${WRAPPER_PATH}/latest" -Force -File | Select-Object -First 1).name
    ${output}=     Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --install --path "${WRAPPER_PATH}/latest/${std_out}" --patch_id ${PATCH_ID} --architecture ${PRODUCT_ARCH} --skip_signature_check 1
    # after: check
    Check Field    ${output}    result.code       1005
    Check Field    ${output}    result.patch_id    12
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: get_product_patch_level
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod-vuln-oft.dat" --sig ${SIGNATURE} --check-feed
    # after: check
    Check Field    ${output}    result.code                    0
    Check Field    ${output}    result.details.count_behind    0
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: Is_defunct
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod.dat" --sig ${SIGNATURE} --check-defunct
    # after: check
    Check Field    ${output}    result.is_defunct    false
    [Teardown]    Teardown VM    windows-10-86

7zip_x86_msi :: windows-10-86 :: DownloadDataBase
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-86
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --path "${WRAPPER_PATH}/vmod-vuln-oft.dat" --get-db vmod-vuln-oft.dat --token OPSWAT_DOWNLOAD_TK_1492e1e57112167a9eb29d7015f7c57d9
    # after: check
    Check Field    ${output}    result.code    0
    [Teardown]    Teardown VM    windows-10-86


# ===========================================================
# ENV: windows-10-64-autologin
# exe_path: C:\Program Files (x86)\7-Zip\7zFM.exe
# Các test sys_acc_* dùng PsExec để chạy dưới SYSTEM account
# ===========================================================

7zip_x86_msi :: windows-10-64-autologin :: download2_with_installed_base
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — install base version trước
    Execute PS    ${WRAPPER_PATH}/Test_script/Proxy.ps1
    Execute PS    & Copy-Item "${INSTALLERS_PATH}/*" -Destination "${WRAPPER_PATH}/" -Recurse
    Execute PS    & Start-Process msiexec.exe -Wait -ArgumentList '/i ${INSTALLERS_PATH_PS}\\${BASE_VERSION}\\${FILE_INSTALLER} /quiet /qn /norestart'
    Execute PS    & Start-Sleep -s 15
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --get --path "${WRAPPER_PATH}/latest" --download 2 --architecture ${PRODUCT_ARCH}
    # after: check
    Check Field    ${output}    result.code       0
    Check Field    ${output}    result.patch_id    12
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: has_vulnerability
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod.dat" --sig ${SIGNATURE} --check-vuln --no-cache
    # after: check
    Check Field    ${output}    result.code              0
    Check Field    ${output}    result.has_vulnerability    true
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: sys_acc_3
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — mở app để test force_close behavior
    Execute PS    Get-WMIObject Win32_InstalledWin32Program | select Name, Version
    Execute PS    ([wmiclass]'root\\cimv2:Win32_Process').Create("C:\\Program Files (x86)\\7-Zip\\7zFM.exe")
    Execute PS    & Start-Sleep -s 15
    Execute PS    ${WRAPPER_PATH}/Test_script/Detect_application.ps1 105 ${SIGNATURE}
    Execute PS    & Start-Sleep -s 15
    Execute PS    ${WRAPPER_PATH}/Test_script/Detect_application.ps1 101 ${SIGNATURE}
    # tested_function — SYSTEM account via PsExec + <std_out> chaining
    ${std_out}=    Execute PS    (Get-ChildItem -Path "${WRAPPER_PATH}/latest" -Force -File | Select-Object -First 1).name
    ${output}=     Execute PS    & "${PS_TOOL}" ${ACCEPT_EULA} "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --install --path "${WRAPPER_PATH}/latest/${std_out}" --force_close 0 --skip_signature_check 1
    # after: check  [NOTE: error.code, không phải result.code]
    Check Field    ${output}    error.code    -1030
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: sys_acc_4
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — (no commands)
    # tested_function — PsExec + <std_out> chaining
    ${std_out}=    Execute PS    (Get-ChildItem -Path "${WRAPPER_PATH}/latest" -Force -File | Select-Object -First 1).name
    ${output}=     Execute PS    & "${PS_TOOL}" ${ACCEPT_EULA} "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --install --path "${WRAPPER_PATH}/latest/${std_out}" --force_close 1 --skip_signature_check 1 --log_dir ${WRAPPER_PATH}
    # after: check
    Check Field    ${output}    result.code    1005
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: sys_acc_get_product_patch_level
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — (no commands)
    # tested_function — PsExec
    ${output}=    Execute PS    & "${PS_TOOL}" ${ACCEPT_EULA} "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod-vuln-oft.dat" --sig ${SIGNATURE} --check-feed
    # after: check
    Check Field    ${output}    result.code                    0
    Check Field    ${output}    result.details.count_behind    0
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: not_has_vulnerability
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — (no commands)
    # tested_function — không có --no-cache (dùng cached result)
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod.dat" --sig ${SIGNATURE} --check-vuln
    # after: check
    Check Field    ${output}    result.code              0
    Check Field    ${output}    result.has_vulnerability    false
    [Teardown]    Teardown VM    windows-10-64-autologin

7zip_x86_msi :: windows-10-64-autologin :: Is_defunct
    [Tags]    REG1    windows    7zip_x86_msi
    [Setup]    Clone And Revert VM    windows-10-64-autologin
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod.dat" --sig ${SIGNATURE} --check-defunct
    # after: check
    Check Field    ${output}    result.is_defunct    false
    [Teardown]    Teardown VM    windows-10-64-autologin


# ===========================================================
# ENV: windows-11-64-autologin   [online: 1 → tag: online]
# exe_path: C:\Program Files (x86)\7-Zip\7zFM.exe
# ===========================================================

7zip_x86_msi :: windows-11-64-autologin :: download_0
    [Tags]    REG1    windows    7zip_x86_msi    online
    [Setup]    Clone And Revert VM    windows-11-64-autologin
    # before — install base version trước
    Execute PS    ${WRAPPER_PATH}/Test_script/Proxy.ps1
    Execute PS    & Copy-Item "${INSTALLERS_PATH}/*" -Destination "${WRAPPER_PATH}/" -Recurse
    Execute PS    & Start-Process msiexec.exe -Wait -ArgumentList '/i ${WRAPPER_PATH_PS}\\${BASE_VERSION}\\${FILE_INSTALLER} /quiet /qn /norestart'
    Execute PS    & Start-Sleep -s 15
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --get --path "${WRAPPER_PATH}/latest" --download 0 --checksum_db "${WRAPPER_PATH}/ap_checksum.dat "
    # after: check
    Check Field    ${output}    result.code    0
    [Teardown]    Teardown VM    windows-11-64-autologin

7zip_x86_msi :: windows-11-64-autologin :: 3
    [Tags]    REG1    windows    7zip_x86_msi    online
    [Setup]    Clone And Revert VM    windows-11-64-autologin
    # before — mở app, detect running
    Execute PS    Get-WMIObject Win32_InstalledWin32Program | select Name, Version
    Execute PS    ([wmiclass]'root\\cimv2:Win32_Process').Create("C:\\Program Files (x86)\\7-Zip\\7zFM.exe")
    Execute PS    & Start-Sleep -s 15
    Execute PS    ${WRAPPER_PATH}/Test_script/Detect_application.ps1 105 ${SIGNATURE}
    Execute PS    & Start-Sleep -s 15
    Execute PS    ${WRAPPER_PATH}/Test_script/Detect_application.ps1 101 ${SIGNATURE}
    # tested_function — force_close 0 + <std_out> chaining
    ${std_out}=    Execute PS    (Get-ChildItem -Path "${WRAPPER_PATH}/latest" -Force -File | Select-Object -First 1).name
    ${output}=     Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --install --path "${WRAPPER_PATH}/latest/${std_out}" --force_close 0 --skip_signature_check 1
    # after: check  [NOTE: error.code]
    Check Field    ${output}    error.code    -1030
    [Teardown]    Teardown VM    windows-11-64-autologin

7zip_x86_msi :: windows-11-64-autologin :: 4
    [Tags]    REG1    windows    7zip_x86_msi    online
    [Setup]    Clone And Revert VM    windows-11-64-autologin
    # before — (no commands)
    # tested_function — force_close 1 + <std_out> chaining
    ${std_out}=    Execute PS    (Get-ChildItem -Path "${WRAPPER_PATH}/latest" -Force -File | Select-Object -First 1).name
    ${output}=     Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/patch.dat" --sig ${SIGNATURE} --install --path "${WRAPPER_PATH}/latest/${std_out}" --force_close 1 --skip_signature_check 1 --log_dir ${WRAPPER_PATH}
    # after: check
    Check Field    ${output}    result.code    1005
    [Teardown]    Teardown VM    windows-11-64-autologin

7zip_x86_msi :: windows-11-64-autologin :: get_product_patch_level
    [Tags]    REG1    windows    7zip_x86_msi    online
    [Setup]    Clone And Revert VM    windows-11-64-autologin
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod-vuln-oft.dat" --sig ${SIGNATURE} --check-feed
    # after: check
    Check Field    ${output}    result.code                    0
    Check Field    ${output}    result.details.count_behind    0
    [Teardown]    Teardown VM    windows-11-64-autologin

7zip_x86_msi :: windows-11-64-autologin :: Is_defunct
    [Tags]    REG1    windows    7zip_x86_msi    online
    [Setup]    Clone And Revert VM    windows-11-64-autologin
    # before — (no commands)
    # tested_function
    ${output}=    Execute PS    & "${WRAPPER_PATH}/test_auto_patching.exe" --db "${WRAPPER_PATH}/vmod.dat" --sig ${SIGNATURE} --check-defunct
    # after: check
    Check Field    ${output}    result.is_defunct    false
    [Teardown]    Teardown VM    windows-11-64-autologin
