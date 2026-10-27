from artin_sentinel.equipment_policy import access_policy, enabled_access_sections


def test_hikvision_recorder_enables_hcnet_only():
    policy=access_policy("Hikvision","dvr")
    sections=enabled_access_sections("Hikvision","dvr")
    assert policy.provider=="hikvision"
    assert policy.sdk_port==8000
    assert sections["hik_sdk"]
    assert not sections["intelbras_sdk"]
    assert not sections["intelbras_cloud"]


def test_intelbras_recorder_enables_netsdk_and_cloud():
    policy=access_policy("Intelbras","xvr")
    sections=enabled_access_sections("Intelbras","xvr")
    assert policy.provider=="intelbras"
    assert policy.sdk_port==37777
    assert sections["intelbras_sdk"]
    assert sections["intelbras_cloud"]
    assert not sections["hik_sdk"]


def test_generic_camera_blocks_proprietary_sdks():
    sections=enabled_access_sections("OEM","camera")
    assert sections["onvif"]
    assert not sections["hik_sdk"]
    assert not sections["intelbras_sdk"]
    assert not sections["intelbras_cloud"]
