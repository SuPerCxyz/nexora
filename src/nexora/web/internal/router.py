"""Internal frontend API router."""

from fastapi import APIRouter

from nexora.web.internal.account import router as account_router
from nexora.web.internal.audit import router as audit_router
from nexora.web.internal.console import router as console_router
from nexora.web.internal.core import router as core_router
from nexora.web.internal.host_onboarding import router as host_onboarding_router
from nexora.web.internal.host_operations import router as host_operations_router
from nexora.web.internal.host_removal import router as host_removal_router
from nexora.web.internal.media import router as media_router
from nexora.web.internal.network import router as network_router
from nexora.web.internal.session import router as session_router
from nexora.web.internal.storage import router as storage_router
from nexora.web.internal.storage_mutations import router as storage_mutations_router
from nexora.web.internal.tasks import router as tasks_router
from nexora.web.internal.vm_changes import router as vm_changes_router
from nexora.web.internal.vm_clone import router as vm_clone_router
from nexora.web.internal.vm_configuration import router as vm_configuration_router
from nexora.web.internal.vm_create import router as vm_create_router
from nexora.web.internal.vm_create_blank import router as vm_create_blank_router
from nexora.web.internal.vm_create_media import router as vm_create_media_router
from nexora.web.internal.vm_lifecycle import router as vm_lifecycle_router
from nexora.web.internal.vm_remove import router as vm_remove_router
from nexora.web.internal.vm_snapshots import router as vm_snapshots_router

router = APIRouter(include_in_schema=False)
router.include_router(core_router)
router.include_router(audit_router)
router.include_router(console_router)
router.include_router(account_router)
router.include_router(session_router)
router.include_router(vm_create_router)
router.include_router(vm_create_blank_router)
router.include_router(host_onboarding_router)
router.include_router(host_operations_router)
router.include_router(host_removal_router)
router.include_router(media_router)
router.include_router(network_router)
router.include_router(vm_create_media_router)
router.include_router(vm_configuration_router)
router.include_router(vm_changes_router)
router.include_router(vm_clone_router)
router.include_router(vm_lifecycle_router)
router.include_router(vm_remove_router)
router.include_router(vm_snapshots_router)
router.include_router(storage_router)
router.include_router(storage_mutations_router)
router.include_router(tasks_router)
