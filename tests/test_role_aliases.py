from onion_sure.backend.security import expand_role_aliases


def test_project_package_imports():
    import onion_sure

    assert onion_sure is not None


def test_required_roles_are_supported():
    assert expand_role_aliases(["SUPER_ADMIN"]) >= {"SUPER_ADMIN", "ADMIN"}
    assert expand_role_aliases(["CENTRE_ADMIN"]) >= {"CENTRE_ADMIN", "OFFICER"}
    assert expand_role_aliases(["AUDITOR"]) >= {"AUDITOR", "REVIEWER"}
    assert expand_role_aliases(["OPERATOR"]) == {"OPERATOR"}
