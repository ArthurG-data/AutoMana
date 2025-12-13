import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
import json
from datetime import datetime
from sqlalchemy.engine import Row
from celery_app.tasks.scryfall import (
    download_scryfall_bulk_uris,
    process_scryfall_bulk_uris,
    download_scryfall_data,
    stage_scryfall_set_data,
    stage_scryfall_card_data,
)


class TestDownloadScryfallBulkUris:
    """Tests for download_scryfall_bulk_uris task"""

    @pytest.fixture
    def mock_connection(self):
        """Mock database connection"""
        conn = MagicMock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        return conn

    @pytest.fixture
    def mock_db_row(self):
        """Mock database row result"""
        return {
            "api_uri": "https://api.scryfall.com/bulk-data",
            "source_id": 1,
            "metadata": {
                "destination": {
                    "path": "scryfall/bulk-data.json"
                }
            }
        }

    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('celery_app.tasks.scryfall.get')
    @patch('celery_app.tasks.scryfall.process_scryfall_bulk_uris.s')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.write_text')
    def test_download_success(
        self, 
        mock_write_text, 
        mock_mkdir, 
        mock_process_task,
        mock_get, 
        mock_get_conn,
        mock_connection,
        mock_db_row
    ):
        """Test successful download of bulk URIs"""
        # Setup
        mock_get_conn.return_value = mock_connection
        mock_execute = mock_connection.execute.return_value
        mock_execute.mappings.return_value.first.return_value = mock_db_row
        
        mock_response = Mock()
        mock_response.text = '{"data": []}'
        mock_response.content = b'{"data": []}'
        mock_get.return_value = mock_response
        
        mock_apply = Mock()
        mock_process_task.return_value.apply_async = mock_apply
        
        # Execute
        download_scryfall_bulk_uris()
        
        # Assert
        mock_get.assert_called_once_with("https://api.scryfall.com/bulk-data")
        mock_mkdir.assert_called_once()
        mock_write_text.assert_called_once()
        mock_apply.assert_called_once()

    @patch('celery_app.tasks.scryfall.get_connection')
    def test_no_resource_found_raises_error(self, mock_get_conn, mock_connection):
        """Test that RuntimeError is raised when no resource found"""
        # Setup
        mock_get_conn.return_value = mock_connection
        mock_execute = mock_connection.execute.return_value
        mock_execute.mappings.return_value.first.return_value = None
        
        # Execute & Assert
        with pytest.raises(RuntimeError, match="No ops.resources row found"):
            download_scryfall_bulk_uris()


class TestProcessScryfallBulkUris:
    """Tests for process_scryfall_bulk_uris task"""

    @pytest.fixture
    def mock_manifest_data(self):
        """Sample manifest data"""
        return {
            "data": [
                {
                    "id": "test-id-1",
                    "type": "default_cards",
                    "uri": "https://api.scryfall.com/bulk-data/test-id-1",
                    "download_uri": "https://data.scryfall.io/default-cards.json",
                    "content_type": "application/json",
                    "content_encoding": "gzip",
                    "updated_at": "2024-01-01T00:00:00.000Z",
                    "size": 100000000,
                    "name": "Default Cards",
                    "description": "All cards in the database"
                }
            ]
        }

    @pytest.fixture
    def task_result(self):
        """Mock task result from previous task"""
        return {
            "source_id": 1,
            "path": "/tmp/manifest.json",
            "bytes": 1000
        }

    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('pathlib.Path.read_text')
    def test_process_manifest_success(
        self,
        mock_read_text,
        mock_get_conn,
        mock_manifest_data,
        task_result
    ):
        """Test successful processing of manifest"""
        # Setup
        mock_read_text.return_value = json.dumps(mock_manifest_data)
        
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_trans = Mock()
        mock_connection.begin.return_value = mock_trans
        
        mock_result = Mock()
        mock_result.mappings.return_value.first.return_value = {
            'resources_upserted': 1,
            'versions_inserted': 1
        }
        mock_connection.execute.return_value = mock_result
        
        # Execute
        result = process_scryfall_bulk_uris(task_result)
        
        # Assert
        assert result["source_id"] == 1
        assert result["resources_upserted"] == 1
        assert result["versions_inserted"] == 1
        mock_trans.commit.assert_called_once()

    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('pathlib.Path.read_text')
    def test_process_manifest_rollback_on_error(
        self,
        mock_read_text,
        mock_get_conn,
        mock_manifest_data,
        task_result
    ):
        """Test rollback when database error occurs"""
        # Setup
        mock_read_text.return_value = json.dumps(mock_manifest_data)
        
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_trans = Mock()
        mock_connection.begin.return_value = mock_trans
        mock_connection.execute.side_effect = Exception("DB Error")
        
        # Execute & Assert
        with pytest.raises(Exception, match="DB Error"):
            process_scryfall_bulk_uris(task_result)
        
        mock_trans.rollback.assert_called_once()


class TestDownloadScryfallData:
    """Tests for download_scryfall_data task"""

    @pytest.fixture
    def mock_db_row(self):
        """Mock database row for resource"""
        return {
            'id': 1,
            'external_id': 'test-external-id',
            'name': 'Default Cards',
            'version_id': 10,
            'download_uri': 'https://data.scryfall.io/default-cards.json',
            'content_type': 'application/json',
            'expected_bytes': 100000000,
            'last_modified': datetime(2024, 1, 1),
            'metadata_updated_at': datetime(2024, 1, 2),
            'metadata_size': '100000000',
            'metadata_download_uri': 'https://data.scryfall.io/default-cards-v2.json'
        }

    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('celery_app.tasks.scryfall.get')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.getsize')
    def test_download_new_file_success(
        self,
        mock_getsize,
        mock_file,
        mock_exists,
        mock_mkdir,
        mock_get,
        mock_get_conn,
        mock_db_row
    ):
        """Test successful download of new file"""
        # Setup
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_execute = mock_connection.execute.return_value
        mock_execute.mappings.return_value.first.return_value = mock_db_row
        
        mock_trans = Mock()
        mock_connection.begin.return_value = mock_trans
        
        mock_response = Mock()
        mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
        mock_get.return_value = mock_response
        
        mock_exists.return_value = False
        mock_getsize.return_value = 100000000
        
        # Execute
        result = download_scryfall_data('default_cards', '/tmp/cards.json')
        
        # Assert
        assert result['status'] == 'downloaded'
        assert result['external_type'] == 'default_cards'
        assert result['bytes_downloaded'] == 100000000
        mock_trans.commit.assert_called_once()

    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('pathlib.Path.exists')
    def test_skip_download_when_up_to_date(
        self,
        mock_exists,
        mock_get_conn,
        mock_db_row
    ):
        """Test skipping download when file is up to date"""
        # Setup
        mock_db_row['last_modified'] = datetime(2024, 1, 3)  # Newer than metadata
        mock_exists.return_value = True
        
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_execute = mock_connection.execute.return_value
        mock_execute.mappings.return_value.first.return_value = mock_db_row
        
        # Execute
        result = download_scryfall_data('default_cards', '/tmp/cards.json')
        
        # Assert
        assert result['status'] == 'skipped'
        assert result['reason'] == 'file_up_to_date'

    @patch('celery_app.tasks.scryfall.get_connection')
    def test_no_resource_raises_error(self, mock_get_conn):
        """Test RuntimeError when no resource found"""
        # Setup
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_execute = mock_connection.execute.return_value
        mock_execute.mappings.return_value.first.return_value = None
        
        # Execute & Assert
        with pytest.raises(RuntimeError, match="No ops.resources row found"):
            download_scryfall_data('default_cards', '/tmp/cards.json')


class TestStageScryfallSetData:
    """Tests for stage_scryfall_set_data task"""

    @pytest.fixture
    def mock_file_path(self, tmp_path):
        """Create a temporary JSON file"""
        file = tmp_path / "sets.json"
        file.write_text('{"data": []}')
        return str(file)

    @patch('backend.new_services.card_catalog.set_service.process_large_sets_json')
    @patch('backend.repositories.card_catalog.set_repository.SetReferenceRepository')
    @patch('backend.request_handling.QueryExecutor.SQLAlchemyQueryExecutor')
    @patch('celery_app.tasks.scryfall.get_connection')
    def test_stage_sets_success(
        self,
        mock_get_conn,
        mock_query_executor,
        mock_set_repository,
        mock_process_func,
        mock_file_path
    ):
        """Test successful staging of set data"""
        # Setup
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_result = Mock()
        mock_result.to_dict.return_value = {
            'sets_processed': 100,
            'sets_inserted': 50
        }
        mock_process_func.return_value = mock_result
        
        # Execute
        result = stage_scryfall_set_data(mock_file_path)
        
        # Assert
        assert result['status'] == 'success'
        assert 'processing_stats' in result
        mock_process_func.assert_called_once()

    def test_file_not_found_raises_error(self):
        """Test FileNotFoundError for non-existent file"""
        with pytest.raises(FileNotFoundError):
            stage_scryfall_set_data('/nonexistent/file.json')

    def test_non_json_file_raises_error(self, tmp_path):
        """Test ValueError for non-JSON file"""
        file = tmp_path / "data.txt"
        file.write_text("not json")
        
        with pytest.raises(ValueError, match="Only JSON files are supported"):
            stage_scryfall_set_data(str(file))

    def test_file_too_large_raises_error(self, tmp_path):
        """Test ValueError for file exceeding size limit"""
        file = tmp_path / "large.json"
        file.write_text('{}')
        
        # Mock the stat to return large size
        with patch.object(Path, 'stat') as mock_stat:
            mock_stat_result = Mock()
            mock_stat_result.st_size = 2 * 1024 * 1024 * 1024  # 2GB
            mock_stat.return_value = mock_stat_result
            
            with pytest.raises(ValueError, match="File too large"):
                stage_scryfall_set_data(str(file))


class TestStageScryfallCardData:
    """Tests for stage_scryfall_card_data task"""

    @pytest.fixture
    def mock_file_path(self, tmp_path):
        """Create a temporary JSON file"""
        file = tmp_path / "cards.json"
        file.write_text('{"data": []}')
        return str(file)

    @patch('backend.new_services.card_catalog.card_service.process_large_cards_json')
    @patch('backend.repositories.card_catalog.card_repository.CardReferenceRepository')
    @patch('backend.request_handling.QueryExecutor.SQLAlchemyQueryExecutor')
    @patch('celery_app.tasks.scryfall.get_connection')
    def test_stage_cards_success(
        self,
        mock_get_conn,
        mock_query_executor,
        mock_card_repository,
        mock_process_func,
        mock_file_path
    ):
        """Test successful staging of card data"""
        # Setup
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_result = Mock()
        mock_result.to_dict.return_value = {
            'cards_processed': 50000,
            'cards_inserted': 25000
        }
        mock_process_func.return_value = mock_result
        
        # Execute
        result = stage_scryfall_card_data(mock_file_path)
        
        # Assert
        assert result['status'] == 'success'
        assert result['processing_stats']['cards_processed'] == 50000
        mock_process_func.assert_called_once()

    @patch('backend.new_services.card_catalog.card_service.process_large_cards_json')
    @patch('backend.repositories.card_catalog.card_repository.CardReferenceRepository')
    @patch('backend.request_handling.QueryExecutor.SQLAlchemyQueryExecutor')
    @patch('celery_app.tasks.scryfall.get_connection')
    def test_database_error_triggers_retry(
        self,
        mock_get_conn,
        mock_query_executor,
        mock_card_repository,
        mock_process_func,
        mock_file_path
    ):
        """Test that database errors are re-raised for Celery retry"""
        # Setup
        mock_connection = MagicMock()
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_connection
        
        mock_process_func.side_effect = Exception("Database connection failed")
        
        # Execute & Assert
        with pytest.raises(Exception, match="Database connection failed"):
            stage_scryfall_card_data(mock_file_path)


# Integration test example
class TestScryfallPipelineIntegration:
    """Integration tests for the full pipeline"""

    @pytest.mark.integration
    @patch('celery_app.tasks.scryfall.get_connection')
    @patch('celery_app.tasks.scryfall.get')
    def test_full_pipeline_flow(self, mock_get, mock_get_conn):
        """Test the full pipeline from download to staging"""
        # This would be a more complex integration test
        # that chains multiple tasks together
        pass


# Fixtures for pytest
@pytest.fixture
def celery_app():
    """Mock Celery app for testing"""
    from celery import Celery
    app = Celery('test')
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    return app