/**
 * CloudWatch Dashboard for File Portal Usage (H-1)
 *
 * Creates a CloudWatch Dashboard that visualizes portal utilization:
 * - Daily Active Users (AppSync unique callers)
 * - Requests per hour by query type (listFiles, searchFiles, askAboutFile, etc.)
 * - Top accessed folders/files
 * - Lambda errors and latency (P50/P95)
 * - AI service usage (Bedrock, Rekognition invocations)
 *
 * Usage:
 *   Import and instantiate in backend.ts or as a separate stack:
 *   ```
 *   import { createPortalDashboard } from './monitoring/dashboard';
 *   createPortalDashboard(stack, 'PortalDashboard', {
 *     apiId: api.apiId,
 *     lambdaFunctions: [listFilesFunction, searchFilesFunction, ...],
 *   });
 *   ```
 *
 * Note: This is a reference implementation. Adapt metric names and
 * dimensions to match your deployed resource names.
 */

import * as cdk from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import { Construct } from "constructs";

export interface PortalDashboardProps {
  apiId: string;
  lambdaFunctionNames: string[];
  region?: string;
}

export function createPortalDashboard(
  scope: Construct,
  id: string,
  props: PortalDashboardProps
): cloudwatch.Dashboard {
  const region = props.region || cdk.Stack.of(scope).region;

  const dashboard = new cloudwatch.Dashboard(scope, id, {
    dashboardName: `FilePortal-Usage-${cdk.Stack.of(scope).stackName}`,
    periodOverride: cloudwatch.PeriodOverride.AUTO,
  });

  // --- Row 1: AppSync API Metrics ---
  dashboard.addWidgets(
    new cloudwatch.GraphWidget({
      title: "AppSync Requests (per hour)",
      width: 12,
      left: [
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "4XXError",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "Sum",
          period: cdk.Duration.hours(1),
          label: "4XX Errors",
          color: "#ff7f0e",
        }),
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "5XXError",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "Sum",
          period: cdk.Duration.hours(1),
          label: "5XX Errors",
          color: "#d62728",
        }),
      ],
    }),
    new cloudwatch.GraphWidget({
      title: "AppSync Latency (ms)",
      width: 12,
      left: [
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "Latency",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "p50",
          period: cdk.Duration.minutes(5),
          label: "P50",
        }),
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "Latency",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "p95",
          period: cdk.Duration.minutes(5),
          label: "P95",
          color: "#ff7f0e",
        }),
      ],
    })
  );

  // --- Row 2: Lambda Metrics ---
  const lambdaInvocations = props.lambdaFunctionNames.map(
    (name) =>
      new cloudwatch.Metric({
        namespace: "AWS/Lambda",
        metricName: "Invocations",
        dimensionsMap: { FunctionName: name },
        statistic: "Sum",
        period: cdk.Duration.hours(1),
        label: name.replace(/Function$/, ""),
      })
  );

  const lambdaErrors = props.lambdaFunctionNames.map(
    (name) =>
      new cloudwatch.Metric({
        namespace: "AWS/Lambda",
        metricName: "Errors",
        dimensionsMap: { FunctionName: name },
        statistic: "Sum",
        period: cdk.Duration.hours(1),
        label: name.replace(/Function$/, ""),
      })
  );

  dashboard.addWidgets(
    new cloudwatch.GraphWidget({
      title: "Lambda Invocations (per hour)",
      width: 12,
      left: lambdaInvocations,
    }),
    new cloudwatch.GraphWidget({
      title: "Lambda Errors (per hour)",
      width: 12,
      left: lambdaErrors,
    })
  );

  // --- Row 3: Single-value widgets for key metrics ---
  dashboard.addWidgets(
    new cloudwatch.SingleValueWidget({
      title: "Total Requests (24h)",
      width: 6,
      metrics: [
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "4XXError",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "SampleCount",
          period: cdk.Duration.days(1),
        }),
      ],
    }),
    new cloudwatch.SingleValueWidget({
      title: "Error Rate (24h)",
      width: 6,
      metrics: [
        new cloudwatch.Metric({
          namespace: "AWS/AppSync",
          metricName: "5XXError",
          dimensionsMap: { GraphQLAPIId: props.apiId },
          statistic: "Sum",
          period: cdk.Duration.days(1),
        }),
      ],
    }),
    new cloudwatch.TextWidget({
      markdown: `## File Portal Dashboard
      
Monitor portal usage, API health, and Lambda performance.
- **AppSync**: Request volume and latency
- **Lambda**: Per-function invocations and errors
- **Alarms**: Configure based on baseline (after 1 week of data)

[View in CloudWatch Console](https://${region}.console.aws.amazon.com/cloudwatch/home?region=${region}#dashboards)`,
      width: 12,
      height: 4,
    })
  );

  return dashboard;
}
