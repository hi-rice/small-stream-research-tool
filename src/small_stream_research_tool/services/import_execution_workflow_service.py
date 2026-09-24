"""Phase 10D orchestration around the existing A/B/C import transactions."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path

from small_stream_research_tool.database import connect_database
from small_stream_research_tool.models.column_mapping import MappingStatus
from small_stream_research_tool.models.import_execution import (
    ImportExecutionRequest,
    ImportSheetSnapshot,
    SourceFileSnapshot,
)
from small_stream_research_tool.models.import_execution_errors import (
    ImportFinalizeError,
    ImportTransactionError,
)
from small_stream_research_tool.models.import_execution_workflow import (
    DuplicateImportConfirmationRequired,
    ImportExecutionOutcome,
    ImportExecutionPlan,
    ImportExecutionSummary,
    ImportExecutionWorkflowError,
    RecoveryRequiredBeforeImport,
)
from small_stream_research_tool.models.import_mapping_workflow import MappingWorkflowState
from small_stream_research_tool.models.workspace import WorkspaceStep
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    ImportHistoryRepository,
    ImportSheetRepository,
    SourceFileRepository,
)
from small_stream_research_tool.repositories.phase10_query_repository import Phase10QueryRepository
from small_stream_research_tool.services.import_execution_service import ImportExecutionService
from small_stream_research_tool.services.import_mapping_workflow_service import (
    ImportMappingWorkflowService,
    MappingWorkflowError,
)
from small_stream_research_tool.services.import_recovery_service import ImportRecoveryService
from small_stream_research_tool.services.phase10_import_policy_service import CORE_ALLOWED
from small_stream_research_tool.services.phase10_read_service import Phase10ReadService
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    load_research_manifest,
    manifest_fingerprint,
)
from small_stream_research_tool.services.research_unit_evidence_service import (
    ResearchUnitEvidenceService,
)
from small_stream_research_tool.services.workspace_service import WorkspaceService
from small_stream_research_tool.utils.file_hash import file_sha256


class ImportExecutionWorkflowService:
    def __init__(self, db_path, workspace_dir=None):
        self._db_path = db_path
        self._workspace_dir = workspace_dir

    def prepare(self, state, user_id):
        if type(state) is not MappingWorkflowState:
            raise ImportExecutionWorkflowError()
        try:
            mapping = ImportMappingWorkflowService(self._db_path, self._workspace_dir)
            fresh, preparation, version_id, policy = mapping.prepare_execution(state, user_id)
            with closing(connect_database(self._db_path)) as connection:
                duplicates = Phase10ReadService(connection).find_duplicate_imports(
                    fresh.source.file_hash
                )
                recovery = ImportRecoveryService(connection).list_recovery_candidates()
            summary = preparation.summary
            mapped = {
                candidate.internal_name
                for candidate in fresh.candidates
                if candidate.internal_name not in CORE_ALLOWED
                and any(
                    item.dictionary_id == candidate.dictionary_id
                    and item.mapping_status
                    in (MappingStatus.AUTO_MAPPED, MappingStatus.USER_MAPPED)
                    for item in fresh.mappings
                )
            }
            excluded = sum(
                item.mapping_status == MappingStatus.DO_NOT_MAP for item in fresh.mappings
            )
            research = load_research_manifest("research-dictionary-v2")
            research_fingerprint = manifest_fingerprint(research)
            evidence_fingerprint = ResearchUnitEvidenceService().load().fingerprint
            public = ImportExecutionSummary(
                fresh.source.file_name,
                fresh.source.selected_sheet,
                summary.total_rows,
                summary.ready_rows,
                summary.excluded_rows,
                summary.create_stream_rows,
                summary.use_existing_stream_rows,
                summary.prepared_value_count,
                len(mapped),
                excluded,
                True,
                any(item.status == "SUCCESS" for item in duplicates),
                bool(recovery),
            )
            return ImportExecutionPlan(
                public,
                fresh,
                preparation,
                version_id,
                research_fingerprint,
                evidence_fingerprint,
                policy,
            )
        except ImportExecutionWorkflowError:
            raise
        except MappingWorkflowError as error:
            raise ImportExecutionWorkflowError(str(error)) from None
        except Exception:
            raise ImportExecutionWorkflowError() from None

    def execute(self, state, user_id, duplicate_confirmed=False, mutation_confirmed=False):
        if not mutation_confirmed:
            raise ImportExecutionWorkflowError("가져오기 실행 확인이 필요합니다.")
        plan = self.prepare(state, user_id)
        if plan.summary.recovery_required:
            raise RecoveryRequiredBeforeImport()
        if plan.summary.duplicate_success and not duplicate_confirmed:
            raise DuplicateImportConfirmationRequired()
        source = plan.workflow_state.source
        path = Path(source.source_path)
        sheet = next(item for item in source.sheets if item.name == source.selected_sheet)
        request = ImportExecutionRequest(
            SourceFileSnapshot(
                source.file_name,
                str(path),
                path.suffix.lower(),
                source.file_size,
                source.file_hash,
            ),
            ImportSheetSnapshot(
                source.selected_sheet,
                source.header_start_row,
                source.header_end_row,
                source.data_start_row,
                sheet.index,
            ),
            plan.preparation,
            plan.workflow_state.mappings,
            user_id,
            dictionary_version_id=plan.dictionary_version_id,
        )
        try:
            with closing(connect_database(self._db_path)) as connection:
                self._verify_execution_prerequisites(connection, plan, path)
                result = ImportExecutionService(connection).execute(
                    request,
                    field_policy=plan.field_policy,
                )
            self._complete_workspace(user_id)
            return self._outcome(result, source, "가져오기가 완료되었습니다.")
        except ImportFinalizeError as error:
            message = (
                "데이터 저장은 완료되었으나 가져오기 상태 복구가 필요합니다."
                if error.result.data_committed
                else "가져오기 데이터는 저장되지 않았으며 상태 점검이 필요합니다."
            )
            return self._outcome(
                error.result,
                source,
                message,
                status="RECOVERY_REQUIRED",
                recovery=True,
            )
        except ImportTransactionError as error:
            return self._outcome(
                error.result,
                source,
                "가져오기에 실패했습니다. 저장 상태를 확인해 주세요.",
                status="FAILED",
            )
        except ImportExecutionWorkflowError:
            raise
        except Exception:
            raise ImportExecutionWorkflowError("가져오기를 실행하지 못했습니다.") from None

    @staticmethod
    def _verify_execution_prerequisites(connection, plan, path):
        current = DictionaryRepository(connection).get_current_version()
        if (
            current is None
            or current.version != "research-dictionary-v2"
            or current.version_id != plan.dictionary_version_id
        ):
            raise ImportExecutionWorkflowError("연구 사전 상태를 확인해야 합니다.")
        research_fingerprint = manifest_fingerprint(load_research_manifest(current.version))
        evidence = ResearchUnitEvidenceService().load()
        if (
            research_fingerprint != plan.research_fingerprint
            or evidence.research_fingerprint != research_fingerprint
            or evidence.fingerprint != plan.evidence_fingerprint
        ):
            raise ImportExecutionWorkflowError("연구 단위 근거를 다시 확인해야 합니다.")
        if file_sha256(path) != plan.workflow_state.source.file_hash:
            raise ImportExecutionWorkflowError(
                "원본 파일이 변경되었습니다. Preview를 다시 확인해 주세요."
            )

    def _complete_workspace(self, user_id):
        workspace = WorkspaceService(self._workspace_dir)
        draft = workspace.load_workspace(user_id)
        if draft is not None:
            workspace.save_workspace(replace(draft, current_step=WorkspaceStep.COMPLETED), user_id)

    @staticmethod
    def _outcome(result, source, message, *, status=None, recovery=False):
        return ImportExecutionOutcome(
            status or result.status,
            source.file_name,
            source.selected_sheet,
            result.ready_rows,
            result.excluded_rows,
            result.created_stream_count,
            result.reused_stream_count,
            result.characteristic_value_count,
            result.started_at,
            result.finished_at,
            recovery,
            message,
        )

    def recover(self, page, page_size, row_index, user_id):
        if not all(type(value) is int for value in (page, page_size, row_index, user_id)):
            raise ImportExecutionWorkflowError("복구할 이력을 다시 선택해 주세요.")
        try:
            with closing(connect_database(self._db_path)) as connection:
                import_ids = Phase10QueryRepository(connection).page_import_ids(
                    page_size, (page - 1) * page_size
                )
                if not 0 <= row_index < len(import_ids):
                    raise ImportExecutionWorkflowError("복구할 이력을 다시 선택해 주세요.")
                import_id = import_ids[row_index]
                inspection = ImportRecoveryService(connection).inspect(import_id)
                if not inspection.can_finalize_success:
                    raise ImportExecutionWorkflowError(
                        "이 이력은 자동 상태 복구 조건을 충족하지 않습니다."
                    )
                ImportRecoveryService(connection).recover_success(import_id)
                try:
                    self._complete_recovered_workspace(connection, import_id, user_id)
                except Exception:
                    return (
                        "가져오기 상태는 SUCCESS로 복구했습니다. "
                        "현재 작업 상태는 다시 확인해 주세요."
                    )
            return "가져오기 상태를 SUCCESS로 복구했습니다."
        except ImportExecutionWorkflowError:
            raise
        except Exception:
            raise ImportExecutionWorkflowError("가져오기 상태를 복구하지 못했습니다.") from None

    def _complete_recovered_workspace(self, connection, import_id, user_id):
        workspace = WorkspaceService(self._workspace_dir)
        draft = workspace.load_workspace(user_id)
        history = ImportHistoryRepository(connection).get_by_id(import_id)
        if draft is None or history is None or history.created_by_user_id != user_id:
            return
        source = SourceFileRepository(connection).get_by_id(history.source_file_id)
        sheets = ImportSheetRepository(connection).list_by_import_id(import_id)
        if (
            source is None
            or source.file_hash != draft.source_file_sha256
            or len(sheets) != 1
            or sheets[0].sheet_name != draft.selected_sheet_name
        ):
            return
        workspace.save_workspace(replace(draft, current_step=WorkspaceStep.COMPLETED), user_id)
