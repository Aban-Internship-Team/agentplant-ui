import {
  ApiError,
  createArtifact,
  createChatTurn,
  deleteConversation,
  getArtifact,
  getArtifactAdaptiveSpec,
  getArtifactPlugin,
  getConversation,
  getHealth,
  listArtifacts,
  listConversations,
  simulatePlant,
  uploadFile,
  validatePlant,
} from "../api/index.ts";
import type {
  ChatMessage,
  ErrorBody,
  PlantModelChatResponse,
  PlantModelConversationDetail,
  PlantModelSessionStateOut,
  PreLaunchConfig,
} from "../types/index.ts";

export type ProbeStepResult = {
  name: string;
  ok: boolean;
  httpStatus?: number;
  message: string;
  response?: unknown;
  error?: {
    name?: string;
    message: string;
    status?: number;
    body?: ErrorBody;
  };
};

export type ProbeReport = {
  ok: boolean;
  total: number;
  passed: number;
  failed: number;
  steps: ProbeStepResult[];
};

class ProbeAssertionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProbeAssertionError";
  }
}

function assertEqual<T>(actual: T, expected: T, label: string): void {
  if (actual !== expected) {
    throw new ProbeAssertionError(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertTruthy(value: unknown, label: string): asserts value {
  if (!value) {
    throw new ProbeAssertionError(`${label}: expected a truthy value`);
  }
}

function assertApiError(error: unknown): asserts error is ApiError {
  if (!(error instanceof ApiError)) {
    const name = error instanceof Error ? error.name : typeof error;
    throw new ProbeAssertionError(`expected ApiError, got ${name}`);
  }
}

function summarize(value: unknown): unknown {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value !== "object") {
    return value;
  }
  try {
    return JSON.parse(JSON.stringify(value)) as unknown;
  } catch {
    return { note: "unserializable value omitted" };
  }
}

function sanitizeError(error: unknown): {
  name?: string;
  message: string;
  status?: number;
  body?: ErrorBody;
} {
  if (error instanceof ApiError) {
    return {
      name: error.name,
      message: error.body.message,
      status: error.status,
      body: error.body,
    };
  }
  if (error instanceof Error) {
    return { name: error.name, message: error.message };
  }
  return { message: "Unexpected probe failure" };
}

function conversationMessages(detail: PlantModelConversationDetail): ChatMessage[] {
  return detail.messages.map((message) => ({
    role: message.role,
    content: message.content,
    status: message.status,
    hitl: message.hitl,
    tool_results: message.tool_results,
    attachment_ids: message.attachment_ids,
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timeseriesOk(value: {
  t: number[];
  x: number[][];
  u: number[][];
  warnings: string[];
}): void {
  if (!Array.isArray(value.t) || !Array.isArray(value.x) || !Array.isArray(value.u)) {
    throw new ProbeAssertionError("simulate response missing t/x/u arrays");
  }
  if (value.t.length === 0 || value.x.length === 0 || value.u.length === 0) {
    throw new ProbeAssertionError("simulate response has empty t/x/u");
  }
  assertEqual(value.t.length, value.x.length, "simulate t/x length");
  assertEqual(value.t.length, value.u.length, "simulate t/u length");
  if (!Array.isArray(value.warnings)) {
    throw new ProbeAssertionError("simulate warnings must be an array");
  }
}

const VALIDATE_PRE_LAUNCH: PreLaunchConfig = {
  total_simulation_time: 1,
  solver_sample_time: 0.25,
  initial_state: [],
  default_target: [],
};

const ARTIFACT_PRE_LAUNCH: PreLaunchConfig = {
  total_simulation_time: 10,
  solver_sample_time: 0.001,
  initial_state: [0, 0],
  default_target: [0, 0],
};

async function nextChatTurn(
  conversationId: number,
  userMessage: string,
  extra: Partial<Parameters<typeof createChatTurn>[0]> = {},
): Promise<PlantModelChatResponse> {
  const detail = await getConversation(conversationId);
  return createChatTurn({
    user_message: userMessage,
    conversation_id: conversationId,
    messages: conversationMessages(detail),
    session_state: detail.session_state,
    ...extra,
  });
}

export async function runContractProbe(): Promise<ProbeReport> {
  const steps: ProbeStepResult[] = [];
  let conversationId: number | undefined;
  let sessionState: PlantModelSessionStateOut | undefined;
  let scopedConversationId: number | undefined;
  let fileId: string | undefined;
  let artifactId: string | undefined;

  const run = async (
    name: string,
    fn: () => Promise<{ httpStatus?: number; message: string; response?: unknown }>,
  ): Promise<boolean> => {
    try {
      const result = await fn();
      steps.push({
        name,
        ok: true,
        httpStatus: result.httpStatus,
        message: result.message,
        response: summarize(result.response),
      });
      return true;
    } catch (error) {
      const sanitized = sanitizeError(error);
      steps.push({
        name,
        ok: false,
        httpStatus: sanitized.status,
        message: sanitized.message,
        error: sanitized,
      });
      return false;
    }
  };

  await run("health", async () => {
    const health = await getHealth();
    assertEqual(health.status, "ok", "health.status");
    assertEqual(health.service, "agent-plant", "health.service");
    return { httpStatus: 200, message: "health ok", response: health };
  });

  await run("chat continue / HITL", async () => {
    const turn = await createChatTurn({ user_message: "hello", messages: [] });
    assertTruthy(turn.conversation_id, "conversation_id");
    assertEqual(turn.status, "continue", "chat status");
    assertTruthy(turn.hitl, "hitl");
    assertTruthy(turn.hitl.question, "hitl.question");
    if (!Array.isArray(turn.hitl.options) || turn.hitl.options.length === 0) {
      throw new ProbeAssertionError("hitl.options must be a non-empty array");
    }
    conversationId = turn.conversation_id ?? undefined;
    sessionState = turn.session_state;
    return {
      httpStatus: 200,
      message: `continue conversation ${String(turn.conversation_id)}`,
      response: {
        conversation_id: turn.conversation_id,
        status: turn.status,
        hitl: turn.hitl,
        session_state: turn.session_state,
      },
    };
  });

  await run("chat draft", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const turn = await nextChatTurn(conversationId, "DC motor");
    assertEqual(turn.status, "draft", "chat status");
    assertEqual(turn.final_result, null, "final_result");
    assertTruthy(turn.session_state.latest_draft, "latest_draft");
    assertEqual(turn.session_state.latest_draft.system_name, "dc_motor", "latest_draft.system_name");
    sessionState = turn.session_state;
    return {
      httpStatus: 200,
      message: "draft dc_motor",
      response: {
        status: turn.status,
        latest_draft: { system_name: turn.session_state.latest_draft.system_name },
        final_result: turn.final_result,
      },
    };
  });

  await run("conversation persistence", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const detail = await getConversation(conversationId);
    assertEqual(detail.id, conversationId, "conversation id");
    if (!Array.isArray(detail.messages) || detail.messages.length < 4) {
      throw new ProbeAssertionError("persisted messages missing expected turns");
    }
    assertTruthy(detail.session_state?.latest_draft, "persisted latest_draft");
    assertEqual(
      detail.session_state.latest_draft.system_name,
      "dc_motor",
      "persisted latest_draft.system_name",
    );
    const firstAssistant = detail.messages.find((message) => message.role === "assistant");
    assertTruthy(firstAssistant?.hitl?.question, "persisted HITL");
    const listed = await listConversations();
    if (!listed.some((item) => item.id === conversationId)) {
      throw new ProbeAssertionError("conversation missing from listConversations");
    }
    sessionState = detail.session_state ?? sessionState;
    return {
      httpStatus: 200,
      message: `persisted ${String(detail.messages.length)} messages`,
      response: {
        id: detail.id,
        status: detail.status,
        message_count: detail.messages.length,
        latest_draft: detail.session_state?.latest_draft
          ? { system_name: detail.session_state.latest_draft.system_name }
          : null,
        listed: listed.some((item) => item.id === conversationId),
      },
    };
  });

  await run("file upload", async () => {
    const file = new File(["contract probe"], "probe.txt", { type: "text/plain" });
    const ref = await uploadFile(file);
    assertTruthy(ref.file_id, "file_id");
    assertEqual(ref.name, "probe.txt", "file name");
    fileId = ref.file_id;
    return { httpStatus: 200, message: `uploaded ${ref.file_id}`, response: ref };
  });

  await run("RAG stub", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    assertTruthy(fileId, "file_id from upload");
    const turn = await nextChatTurn(conversationId, "DC motor attachment", {
      attachment_ids: [fileId],
    });
    if (!turn.tool_results.some((item) => item.kind === "rag")) {
      throw new ProbeAssertionError("tool_results missing kind=rag");
    }
    sessionState = turn.session_state;
    return {
      httpStatus: 200,
      message: "rag tool_results present",
      response: { status: turn.status, kinds: turn.tool_results.map((item) => item.kind) },
    };
  });

  await run("web search stub", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const turn = await nextChatTurn(conversationId, "DC motor search", { web_search: true });
    if (!turn.tool_results.some((item) => item.kind === "search")) {
      throw new ProbeAssertionError("tool_results missing kind=search");
    }
    sessionState = turn.session_state;
    return {
      httpStatus: 200,
      message: "search tool_results present",
      response: { status: turn.status, kinds: turn.tool_results.map((item) => item.kind) },
    };
  });

  await run("sandbox simulation from draft", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const sim = await simulatePlant({
      conversation_id: conversationId,
      total_simulation_time: 1,
      solver_sample_time: 0.25,
      amplitude: 1,
    });
    timeseriesOk(sim);
    if (sim.x[0].length !== 2) {
      throw new ProbeAssertionError(`expected sandbox 2-state draft, got x[0].length=${String(sim.x[0].length)}`);
    }
    return {
      httpStatus: 200,
      message: "sandbox trajectory from draft",
      response: { samples: sim.t.length, state_dim: sim.x[0].length, warnings: sim.warnings },
    };
  });

  await run("mock simulation fallback", async () => {
    const sim = await simulatePlant({
      total_simulation_time: 1,
      solver_sample_time: 0.25,
    });
    timeseriesOk(sim);
    if (sim.x[0].length !== 1) {
      throw new ProbeAssertionError(`expected mock 1-state trajectory, got x[0].length=${String(sim.x[0].length)}`);
    }
    return {
      httpStatus: 200,
      message: "mock trajectory without plant",
      response: { samples: sim.t.length, state_dim: sim.x[0].length, warnings: sim.warnings },
    };
  });

  await run("finish chat", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const turn = await nextChatTurn(conversationId, "finish");
    assertEqual(turn.status, "complete", "chat status");
    assertTruthy(turn.final_result, "final_result");
    assertEqual(turn.final_result.system_name, "dc_motor", "final_result.system_name");
    sessionState = turn.session_state;
    return {
      httpStatus: 200,
      message: "conversation complete",
      response: {
        status: turn.status,
        system_name: turn.final_result.system_name,
        session_state: sessionState,
      },
    };
  });

  await run("validate", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const result = await validatePlant({
      conversation_id: conversationId,
      pre_launch: VALIDATE_PRE_LAUNCH,
    });
    if (typeof result.ok !== "boolean") {
      throw new ProbeAssertionError("validate.ok must be boolean");
    }
    if (!Array.isArray(result.errors) || !Array.isArray(result.warnings)) {
      throw new ProbeAssertionError("validate errors/warnings must be arrays");
    }
    return {
      httpStatus: 200,
      message: result.ok ? "validation ok" : "logical validation failure kept HTTP 200",
      response: result,
    };
  });

  await run("artifact create and read", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    const created = await createArtifact({
      conversation_id: conversationId,
      pre_launch: ARTIFACT_PRE_LAUNCH,
    });
    assertTruthy(created.artifact_id, "artifact_id");
    artifactId = created.artifact_id;
    const listed = await listArtifacts();
    if (!listed.some((item) => item.artifact_id === artifactId)) {
      throw new ProbeAssertionError("created artifact missing from list");
    }
    const detail = await getArtifact(artifactId);
    assertEqual(detail.artifact_id, artifactId, "artifact detail id");
    if (!isRecord(detail.plant) || !isRecord(detail.pre_launch)) {
      throw new ProbeAssertionError("artifact detail missing plant/pre_launch objects");
    }
    const plugin = await getArtifactPlugin(artifactId);
    assertEqual(plugin.artifact_id, artifactId, "plugin artifact_id");
    assertTruthy(plugin.source, "plugin source");
    const spec = await getArtifactAdaptiveSpec(artifactId);
    if (!isRecord(spec)) {
      throw new ProbeAssertionError("adaptive-spec must be an object");
    }
    return {
      httpStatus: 201,
      message: `artifact ${artifactId}`,
      response: {
        created,
        listed: listed.length,
        detail: { artifact_id: detail.artifact_id, system_name: detail.system_name },
        plugin: { artifact_id: plugin.artifact_id, source_chars: plugin.source.length },
        adaptive_spec_keys: Object.keys(spec),
      },
    };
  });

  await run("error 422", async () => {
    try {
      await simulatePlant({
        total_simulation_time: 1,
        solver_sample_time: 0,
      });
    } catch (error) {
      assertApiError(error);
      assertEqual(error.status, 422, "status");
      assertTruthy(error.body.message, "ErrorBody.message");
      if (!Array.isArray(error.body.errors) || !Array.isArray(error.body.warnings)) {
        throw new ProbeAssertionError("ErrorBody arrays missing");
      }
      return {
        httpStatus: 422,
        message: "structured 422 ErrorBody",
        response: error.body,
      };
    }
    throw new ProbeAssertionError("expected ApiError 422");
  });

  await run("error 404", async () => {
    try {
      await getConversation(999999);
    } catch (error) {
      assertApiError(error);
      assertEqual(error.status, 404, "status");
      assertTruthy(error.body.message, "ErrorBody.message");
      if (!Array.isArray(error.body.errors) || !Array.isArray(error.body.warnings)) {
        throw new ProbeAssertionError("ErrorBody arrays missing");
      }
      return { httpStatus: 404, message: "structured 404 ErrorBody", response: error.body };
    }
    throw new ProbeAssertionError("expected ApiError 404");
  });

  await run("error 403", async () => {
    const owned = await createChatTurn(
      { user_message: "hello", messages: [] },
      { userId: 1 },
    );
    assertTruthy(owned.conversation_id, "scoped conversation_id");
    scopedConversationId = owned.conversation_id ?? undefined;
    try {
      await getConversation(owned.conversation_id as number, { userId: 2 });
    } catch (error) {
      assertApiError(error);
      assertEqual(error.status, 403, "status");
      assertTruthy(error.body.message, "ErrorBody.message");
      if (!Array.isArray(error.body.errors) || !Array.isArray(error.body.warnings)) {
        throw new ProbeAssertionError("ErrorBody arrays missing");
      }
      return { httpStatus: 403, message: "structured 403 ErrorBody", response: error.body };
    }
    throw new ProbeAssertionError("expected ApiError 403");
  });

  await run("error 400", async () => {
    try {
      await uploadFile(new File([], "empty.txt"));
    } catch (error) {
      assertApiError(error);
      assertEqual(error.status, 400, "status");
      assertTruthy(error.body.message, "ErrorBody.message");
      if (!Array.isArray(error.body.errors) || !Array.isArray(error.body.warnings)) {
        throw new ProbeAssertionError("ErrorBody arrays missing");
      }
      return { httpStatus: 400, message: "structured 400 ErrorBody", response: error.body };
    }
    throw new ProbeAssertionError("expected ApiError 400");
  });

  await run("delete conversation", async () => {
    assertTruthy(conversationId, "conversation_id from prior step");
    await deleteConversation(conversationId);
    try {
      await getConversation(conversationId);
    } catch (error) {
      assertApiError(error);
      assertEqual(error.status, 404, "status after delete");
      return {
        httpStatus: 204,
        message: "deleted; subsequent GET is 404",
        response: error.body,
      };
    }
    throw new ProbeAssertionError("expected 404 after delete");
  });

  if (scopedConversationId !== undefined) {
    try {
      await deleteConversation(scopedConversationId, { userId: 1 });
    } catch {
      // cleanup only; do not fail the report
    }
  }

  const passed = steps.filter((step) => step.ok).length;
  const failed = steps.length - passed;
  return {
    ok: failed === 0,
    total: steps.length,
    passed,
    failed,
    steps,
  };
}
