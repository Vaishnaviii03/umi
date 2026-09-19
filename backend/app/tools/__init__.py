"""Phase 3 — tool system package.

Importing this package registers the built-in tools on the shared
``tool_registry`` so the LLM tool-calling glue and the API can use them.
"""

from app.tools.base import (  # noqa: F401
    ConfirmationRequired,
    EmptyArgs,
    PermissionDenied,
    Tool,
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFound,
    ToolOutputError,
    ToolResult,
)

from app.tools.registry import tool_registry  # noqa: F401
from app.tools.manager import tool_manager  # noqa: F401  (re-export for routes/llm)
from app.tools.builtin import CalculateTool, GetTimeTool  # noqa: F401  (register side effects)
from app.tools.tasks import (  # noqa: F401  (register side effects)
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    ListTasksTool,
    UpdateTaskTool,
)
from app.tools.gmail import (  # noqa: F401  (register side effects)
    ComposeDraftTool,
    GetEmailTool,
    ListEmailsTool,
    SearchEmailsTool,
    SendEmailTool,
    SummarizeEmailsTool,
)
from app.tools.calendar import (  # noqa: F401  (register side effects)
    CreateEventTool,
    DeleteEventTool,
    ListEventsTool,
    SummarizeCalendarTool,
    UpdateEventTool,
)
from app.tools.google import (  # noqa: F401  (register side effects)
    GoogleCreateDocumentTool,
    GoogleCreateSpreadsheetTool,
    GoogleFindDocumentTool,
    GoogleFindSpreadsheetTool,
    GoogleReadDocumentTool,
    GoogleReadDriveFileTool,
    GoogleReadSheetTool,
    GoogleSearchDriveTool,
    GoogleSearchYoutubeTool,
    GoogleUpdateDocumentTool,
    GoogleWriteSheetTool,
    GoogleYoutubeDeleteVideoTool,
    GoogleYoutubeListUploadsTool,
    GoogleYoutubeUpdateVideoTool,
    GoogleYoutubeUploadVideoTool,
    GoogleYoutubeVideoInfoTool,
)

tool_registry.register(CalculateTool)
tool_registry.register(GetTimeTool)
tool_registry.register(CreateTaskTool)
tool_registry.register(ListTasksTool)
tool_registry.register(CompleteTaskTool)
tool_registry.register(UpdateTaskTool)
tool_registry.register(DeleteTaskTool)
tool_registry.register(ListEmailsTool)
tool_registry.register(GetEmailTool)
tool_registry.register(SearchEmailsTool)
tool_registry.register(SummarizeEmailsTool)
tool_registry.register(ComposeDraftTool)
tool_registry.register(SendEmailTool)
tool_registry.register(ListEventsTool)
tool_registry.register(SummarizeCalendarTool)
tool_registry.register(CreateEventTool)
tool_registry.register(UpdateEventTool)
tool_registry.register(DeleteEventTool)
tool_registry.register(GoogleSearchDriveTool)
tool_registry.register(GoogleReadDriveFileTool)
tool_registry.register(GoogleFindSpreadsheetTool)
tool_registry.register(GoogleReadSheetTool)
tool_registry.register(GoogleWriteSheetTool)
tool_registry.register(GoogleCreateSpreadsheetTool)
tool_registry.register(GoogleFindDocumentTool)
tool_registry.register(GoogleReadDocumentTool)
tool_registry.register(GoogleCreateDocumentTool)
tool_registry.register(GoogleUpdateDocumentTool)
tool_registry.register(GoogleSearchYoutubeTool)
tool_registry.register(GoogleYoutubeVideoInfoTool)
tool_registry.register(GoogleYoutubeListUploadsTool)
tool_registry.register(GoogleYoutubeUpdateVideoTool)
tool_registry.register(GoogleYoutubeUploadVideoTool)
tool_registry.register(GoogleYoutubeDeleteVideoTool)
from app.tools.vision import DescribeVisualSceneTool  # noqa: E402
tool_registry.register(DescribeVisualSceneTool)