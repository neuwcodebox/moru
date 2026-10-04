from unittest.mock import Mock

import pytest

from moru.errors import MoruError
from moru.windows_job import WindowsJob


def test_closing_owned_windows_job_releases_the_process_tree_exactly_once():
    kernel = Mock()
    kernel.CreateJobObjectW.return_value = 123
    job = WindowsJob(kernel)
    job.assign(456)
    kernel.AssignProcessToJobObject.assert_called_once_with(123, 456)
    job.close()
    job.close()
    kernel.CloseHandle.assert_called_once_with(123)


def test_worker_start_fails_if_windows_cannot_guarantee_child_cleanup():
    kernel = Mock()
    kernel.CreateJobObjectW.return_value = 123
    kernel.SetInformationJobObject.return_value = False
    with pytest.raises(MoruError) as error:
        WindowsJob(kernel)
    assert error.value.code == "IMAGE_WORKER_START_FAILED"
    kernel.CloseHandle.assert_called_once_with(123)
