import type {
  AnalysisWorkflowRequest,
  AnalysisWorkflowResponse,
} from "./types";

interface FastAPIValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

interface ErrorPayload {
  detail?: string | FastAPIValidationIssue[];
}

function readableError(status: number, payload: ErrorPayload | null): string {
  if (Array.isArray(payload?.detail)) {
    const firstIssue = payload.detail[0];
    const field = firstIssue?.loc?.at(-1);
    return `${field ? `${String(field)}：` : ""}${firstIssue?.msg ?? "请求参数不正确"}`;
  }

  if (typeof payload?.detail === "string") {
    const knownMessages: Record<string, string> = {
      "The candidate information cannot be processed.":
        "候选人信息无法处理，请检查候选人 ID 或邮箱。",
      "The workflow analysis results are inconsistent.":
        "分析结果出现技能映射不一致，请稍后重试。",
      "The LLM returned invalid or empty output.":
        "AI 返回结果不完整，请稍后再试。",
      "The LLM provider is temporarily rate-limited. Please try again later.":
        "AI 服务当前请求较多，请稍后再试。",
      "The LLM service is temporarily unavailable. Please try again later.":
        "AI 服务暂时不可用，请稍后再试。",
      "The LLM provider returned an error.":
        "AI 服务返回异常，请稍后再试。",
      "The database service is temporarily unavailable.":
        "数据服务暂时不可用，请稍后再试。",
      "The workflow conflicts with existing stored data.":
        "本次分析与已有数据冲突，请检查候选人信息。",
    };
    return knownMessages[payload.detail] ?? payload.detail;
  }

  if (status >= 500) {
    return "服务暂时无法完成分析，请稍后再试。";
  }
  return "请求未成功，请检查输入后重试。";
}

export async function analyzeWorkflow(
  request: AnalysisWorkflowRequest,
): Promise<AnalysisWorkflowResponse> {
  const response = await fetch("/analyze/workflow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let payload: ErrorPayload | null = null;
    try {
      payload = (await response.json()) as ErrorPayload;
    } catch {
      payload = null;
    }
    throw new Error(readableError(response.status, payload));
  }

  return (await response.json()) as AnalysisWorkflowResponse;
}
