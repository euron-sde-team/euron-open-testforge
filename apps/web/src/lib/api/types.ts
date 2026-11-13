/**
 * Named aliases over the generated OpenAPI types (`pnpm gen:api`). Nothing here is
 * hand-written: every shape comes from `schema.d.ts`, which is generated from
 * docs/api/openapi.yaml.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type SignIn = S["SignInOut"];
export type AuditEntry = S["AuditOut"];
export type AuditPage = S["Page_AuditOut_"];
export type SystemInfo = S["SystemInfo"];
export type QueueInfo = S["QueueInfo"];
export type Role = NonNullable<UserCreate["role"]>;
export type PublicSettings = S["PublicSettings"];
export type AdminSettings = S["AdminSettings"];
export type SettingsUpdate = S["SettingsUpdate"];

export type Org = S["OrgOut"];
export type OrgRole = NonNullable<Org["role"]>;
export type OrgMember = S["OrgMemberOut"];
export type OrgMemberAdd = S["OrgMemberAdd"];

export type Project = S["ProjectOut"];
export type ProjectCreate = S["ProjectCreate"];
export type ProjectUpdate = S["ProjectUpdate"];
export type ProjectRole = NonNullable<Project["role"]>;
export type Member = S["MemberOut"];
export type ApiKey = S["ApiKeyOut"];
export type ApiKeyCreated = S["ApiKeyCreated"];
export type Scope = NonNullable<S["ApiKeyCreate"]["scopes"]>[number];

export type Provider = S["ProviderOut"];
export type ProviderCreate = S["ProviderCreate"];
export type ProviderUpdate = S["ProviderUpdate"];
export type ProviderKind = Provider["kind"];
export type ProviderTest = S["ProviderTest"];

export type Import = S["ImportOut"];
export type ImportStatus = Import["status"];
export type ImportKind = Import["kind"];
export type GitHubImport = S["GitHubImport"];
export type Analysis = S["AnalysisOut"];
export type Unit = S["UnitOut"];
export type UnitDetail = S["UnitDetail"];
export type UnitKind = Unit["kind"];
export type SourceFile = S["FileOut"];
export type FileContent = S["FileContent"];

export type Spec = S["SpecOut"];
export type Operation = S["OperationOut"];

export type Pull = S["PullOut"];
export type PullDetail = S["PullDetail"];

export type GenerateRequest = S["GenerateRequest"];
export type TestKind = NonNullable<GenerateRequest["kinds"]>[number];
export type Generation = S["GenerationOut"];
export type GenerationStatus = Generation["status"];
export type Rejection = S["Rejection"];
export type GeneratedTest = S["TestOut"];
export type TestDetail = S["TestDetail"];
export type TestStatus = GeneratedTest["status"];
export type Assertion = S["AssertionOut"];
export type BulkReview = S["BulkReview"];

export type RunCreate = S["RunCreate"];
export type RunKind = NonNullable<RunCreate["kind"]>;
export type Run = S["RunOut"];
export type RunDetail = S["RunDetail"];
export type RunStatus = Run["status"];
export type LimitName = NonNullable<Run["limit_exceeded"]>;
export type TestCase = S["CaseOut"];
export type CaseOutcome = TestCase["outcome"];
export type Failure = S["FailureOut"];
export type AnalyzeRequest = S["AnalyzeRequest"];

export type Coverage = S["CoverageOut"];
export type ProjectCoverage = S["ProjectCoverage"];
export type TrendPoint = S["TrendPoint"];
export type Point = S["Point"];

export type Report = S["ReportOut"];
export type ReportCreate = S["ReportCreate"];

export type Webhook = S["WebhookOut"];
export type WebhookCreate = S["WebhookCreate"];
export type WebhookCreated = S["WebhookCreated"];
export type WebhookEvent = NonNullable<WebhookCreate["events"]>[number];
export type Delivery = S["DeliveryOut"];
export type GitHubSecret = S["GitHubSecret"];

export type Overview = S["Overview"];
export type UsageReport = S["UsageReport"];
export type UsageDay = S["UsageByDay"];
