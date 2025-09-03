import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.new_services.user_management.role_service import assign_role, has_role_permission, has_role
from backend.schemas.user_management.role import AssignRoleRequest, Role
from backend.exceptions.user_management import role_exceptions
from backend.schemas.user_management import user
from uuid import UUID

@pytest.fixture
def mock_role_repo():
    """Create a mock repository with AsyncMock methods"""
    repo = MagicMock()
    repo.get_role_by_name = AsyncMock()
    repo.assign_role = AsyncMock()
    repo.user_has_role = AsyncMock()
    repo.user_has_permission = AsyncMock()
    return repo

@pytest.fixture
def mock_user():
    return user.UserInDB(
        unique_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        username="testuser",
        email="testuser@example.com",
        hashed_password="hashedpassword",
        disabled=False
    )


@pytest.mark.asyncio
async def test_assign_role_success(mock_role_repo): 
    """Test assigning a role successfully"""
    user_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    role_request = AssignRoleRequest(role=Role.admin)

    mock_role_repo.get_role_by_name.return_value = {"role": "admin"}
    mock_role_repo.assign_role.return_value = True

    result = await assign_role(mock_role_repo, user_id, role_request)

    assert result["success"] is True
    assert result["user_id"] == str(user_id)
    assert result["role"] == "admin"

@pytest.mark.asyncio
async def test_assign_role_not_found(mock_role_repo):
    """Test assigning a role that does not exist"""
    user_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    role_request = AssignRoleRequest(role=Role.developer)

    mock_role_repo.get_role_by_name.return_value = None

    with pytest.raises(role_exceptions.RoleNotFoundError):
        await assign_role(mock_role_repo, user_id, role_request)  
    mock_role_repo.get_role_by_name.assert_called_once_with(role_request.role.value)
    mock_role_repo.assign_role.assert_not_called()

@pytest.mark.asyncio
async def test_assign_role_repository_error(mock_role_repo):
    """Test handling repository errors during role assignment"""
    user_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    role_request = AssignRoleRequest(role=Role.tester)

    mock_role_repo.get_role_by_name.side_effect = Exception("Database error")

    with pytest.raises(role_exceptions.RoleAssignmentError):
        await assign_role(mock_role_repo, user_id, role_request)
    
    mock_role_repo.get_role_by_name.assert_called_once_with(role_request.role.value)
    mock_role_repo.assign_role.assert_not_called()

@pytest.mark.asyncio
async def test_has_role_permission_success(mock_role_repo, mock_user):
    """Test checking role permission successfully"""
    permission = "admin"

    mock_role_repo.user_has_permission.return_value = {"exists": True}

    result = await has_role_permission(mock_role_repo, permission, mock_user)

    assert result is True
    mock_role_repo.user_has_permission.assert_called_once_with(mock_user.unique_id, permission)

@pytest.mark.asyncio
async def test_has_role_permission_not_found(mock_role_repo, mock_user):
    """Test checking role permission not found"""
    permission = "admin"

    mock_role_repo.user_has_permission.return_value = {"exists": False}

    with pytest.raises(role_exceptions.PermissionNotFoundError):
        await has_role_permission(mock_role_repo, permission, mock_user)
    mock_role_repo.user_has_permission.assert_called_once_with(mock_user.unique_id, permission)

@pytest.mark.asyncio
async def test_has_role_permission_repository_error(mock_role_repo, mock_user):
    """Test handling repository errors during role permission check"""
    permission = "admin"    
    mock_role_repo.user_has_permission.side_effect = Exception("Database error")
    with pytest.raises(role_exceptions.RoleRepositoryError):
        await has_role_permission(mock_role_repo, permission, mock_user)
    mock_role_repo.user_has_permission.assert_called_once_with(mock_user.unique_id, permission)
    mock_role_repo.assign_role.assert_not_called()

@pytest.mark.asyncio
async def test_has_role_success(mock_role_repo, mock_user):
    """Test checking if user has a specific role"""
    role_name = "admin"

    mock_role_repo.user_has_role.return_value = {"exists": True}

    result = await has_role(mock_role_repo, role_name, mock_user)

    assert result is True
    mock_role_repo.user_has_role.assert_called_once_with(mock_user.unique_id, role_name)

@pytest.mark.asyncio
async def test_has_role_not_found(mock_role_repo, mock_user):
    """Test checking if user has a specific role"""
    role_name = "admin"

    mock_role_repo.user_has_role.return_value = {"exists": False}

    with pytest.raises(role_exceptions.RoleNotFoundError):
        await has_role(mock_role_repo, role_name, mock_user)
    mock_role_repo.user_has_role.assert_called_once_with(mock_user.unique_id, role_name)

@pytest.mark.asyncio
async def test_has_role_repository_error(mock_role_repo, mock_user):
    """Test handling repository errors during role check"""
    role_name = "admin"

    mock_role_repo.user_has_role.side_effect = Exception("Database error")

    with pytest.raises(role_exceptions.RoleRepositoryError):
        await has_role(mock_role_repo, role_name, mock_user)
    
    mock_role_repo.user_has_role.assert_called_once_with(mock_user.unique_id, role_name)
    mock_role_repo.assign_role.assert_not_called()