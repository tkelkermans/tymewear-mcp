"""Tests for Pydantic response models."""

from tymewear_mcp.client.models import Activity, ActivityDetail, Profile


class TestProfile:
    def test_parse_profile(self):
        data = {
            "id": 99999,
            "email": "test@example.com",
            "gender": "M",
            "units": "SI",
            "is_active": True,
            "weight": 70.0,
            "weight_units": "SI",
            "birthday": "2000 Jan 01",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "raw_data_access": False,
            "height": 178,
            "height_units": "SI",
            "user_type": "trainee",
            "first_name": "Test",
            "last_name": "User",
            "external_accounts": {"GARMIN": "2025-01-01T00:00:00Z"},
            "bike_ve_target_vt1": 60.0,
            "bike_ve_target_bp": 80.0,
            "bike_ve_target_vt2": 110.0,
            "bike_ve_target_vo2max": 160.0,
            "running_ve_target_vt1": 0.0,
            "running_ve_target_bp": 0.0,
            "running_ve_target_vt2": 0.0,
            "running_ve_target_vo2max": 0.0,
            "zone_targets": [0, 0, 0, 0, 0],
            "toc_accepted": True,
            "toc_accepted_at": "2025-01-01T00:00:00Z",
            "workout_recommendation_access": False,
            "subscription_tier": "paid",
            "subscription_status": "active",
        }
        profile = Profile.model_validate(data)
        assert profile.id == 99999
        assert profile.bike_ve_target_vt1 == 60.0
        assert profile.subscription_tier == "paid"
        assert profile.external_accounts == {"GARMIN": "2025-01-01T00:00:00Z"}

    def test_profile_allows_extra_fields(self):
        """API may return fields we don't model yet."""
        data = {
            "id": 1, "email": "t@t.com", "gender": "M", "units": "SI",
            "is_active": True, "weight": 70.0, "weight_units": "SI",
            "birthday": "2000 Jan 01", "uuid": "abc", "raw_data_access": False,
            "height": 180, "height_units": "SI", "user_type": "trainee",
            "first_name": "A", "last_name": "B", "external_accounts": {},
            "bike_ve_target_vt1": 0, "bike_ve_target_bp": 0,
            "bike_ve_target_vt2": 0, "bike_ve_target_vo2max": 0,
            "running_ve_target_vt1": 0, "running_ve_target_bp": 0,
            "running_ve_target_vt2": 0, "running_ve_target_vo2max": 0,
            "zone_targets": [], "toc_accepted": True, "toc_accepted_at": None,
            "workout_recommendation_access": False, "subscription_tier": "free",
            "subscription_status": "active", "some_future_field": "value",
        }
        profile = Profile.model_validate(data)
        assert profile.id == 1


class TestActivity:
    def test_parse_activity(self):
        data = {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": "Normal Activity", "type": "0", "type_display": "Normal Activity",
            "sport": "2", "sport_display": "Bike",
            "time_stamp": "2025 Jan 15 10:00:00", "tz_offset": "2.0",
            "pinned": False, "was_pinned": False, "vt1": "", "vt2": "", "v02max": "",
            "duration": "24:24", "duration_seconds": 1464, "user": 99999,
            "pinned_status": None, "algo_status": "success",
            "app_version": "1.3.8 - 1115", "firmware_version": "0.73",
            "hardware_version": "8", "hr_firmware_version": "",
            "baseline": None, "max_amp": None, "fev1": None, "pod_id": "",
            "garmin_iq_app_v": None, "battery_life": 97, "data_type": "tyme-wear",
            "success_rate": "-", "kcal_expenditure": None,
            "zones_distribution_summary_table": [],
            "new_zone_distribution_summary_table": [],
        }
        activity = Activity.model_validate(data)
        assert activity.id == "00000000-0000-0000-0000-000000000002"
        assert activity.sport_display == "Bike"
        assert activity.duration_seconds == 1464


class TestActivityDetail:
    def test_parse_activity_detail(self):
        data = {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": "Normal Activity", "type": "0", "type_display": "Normal Activity",
            "sport": "2", "sport_display": "Bike",
            "time_stamp": "2025-01-15T10:00:00Z", "tz_offset": "2.0",
            "pinned": False, "was_pinned": False, "vt1": "", "vt2": "", "v02max": "",
            "duration": "24:24", "duration_seconds": 1464, "user": 99999,
            "pinned_status": None, "algo_status": "success",
            "app_version": "1.3.8 - 1115", "firmware_version": "0.73",
            "hardware_version": "8", "hr_firmware_version": "",
            "baseline": None, "max_amp": None, "fev1": None, "pod_id": "",
            "garmin_iq_app_v": None, "battery_life": 97, "data_type": "tyme-wear",
            "success_rate": "-", "kcal_expenditure": None,
            "zones_distribution_summary_table": [],
            "new_zone_distribution_summary_table": [],
            "algo_version": "2.44", "placeholder": False,
            "unix_timestamp": 1700000000, "tz_name": "CEST",
            "intervals": {}, "third_party_activities": [], "is_bike": True,
            "admin_notes": "", "ext_hr": [], "ext_bike_power": [],
            "ext_cadence": [], "ext_speed": [], "zones": [], "tss": None,
            "balance_point": "", "strap_model": None, "shirt_id": "",
            "fs": None, "imu_fs": None,
        }
        detail = ActivityDetail.model_validate(data)
        assert detail.algo_version == "2.44"
        assert detail.is_bike is True
        assert detail.unix_timestamp == 1700000000
