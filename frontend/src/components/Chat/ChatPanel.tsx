/**
 * Chat panel with scrollable step timeline.
 */

import { useRef, useEffect } from 'react';
import { Sender } from '@ant-design/x';
import { Typography, Tag, Spin, Avatar, Button } from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  ThunderboltOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useSessionStore } from '../../store/sessionStore';
import type { Message, AgentStep } from '../../types';
import styles from './ChatPanel.module.css';

const { Text } = Typography;

interface ChatPanelProps {
  onSendMessage: (message: string) => void;
}

// Format duration in seconds to display string (e.g., "1.233秒")
const formatDuration = (duration?: number): string => {
  if (!duration) return '';
  return `${duration.toFixed(3)}秒`;
};

export function ChatPanel({ onSendMessage }: ChatPanelProps) {
  const { messages, isProcessing, currentSession, stopTask } = useSessionStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (content: string) => {
    if (content.trim() && !isProcessing) {
      onSendMessage(content.trim());
    }
  };

  const renderUserMessage = (message: Message) => (
    <div key={message.id} className={styles.messageRow}>
      <div className={styles.userMessage}>
        <div className={styles.messageText}>{message.content}</div>
        <Avatar 
          icon={<UserOutlined />} 
          size={32}
          className={styles.userAvatar}
        />
      </div>
    </div>
  );

  const renderActionDetails = (action: Record<string, unknown>) => {
    const details: string[] = [];

    if (action.element) {
      details.push(`坐标 [${(action.element as number[]).join(', ')}]`);
    }
    if (action.text) {
      details.push(`"${action.text}"`);
    }
    if (action.app) {
      details.push(`${action.app}`);
    }
    if (action.start && action.end) {
      details.push(`从 [${(action.start as number[]).join(',')}] 到 [${(action.end as number[]).join(',')}]`);
    }
    if (action.message && (action._metadata === 'finish' || action.action === 'Take_over')) {
      return (
        <Text className={styles.actionMessage}>{action.message as string}</Text>
      );
    }

    if (details.length === 0) return null;

    return (
      <Text type="secondary" className={styles.actionParams}>
        {details.join(' · ')}
      </Text>
    );
  };

  const renderStep = (step: AgentStep, isLast: boolean) => {
    const isThinking = step.status === 'thinking';
    const actionType = step.action?.action || step.action?._metadata;

    return (
      <div key={step.id} className={styles.stepItem}>
        {/* Step indicator */}
        <div className={styles.stepIndicator}>
          <div className={`${styles.stepNumber} ${isThinking ? styles.thinking : styles.completed}`}>
            {isThinking ? (
              <LoadingOutlined spin />
            ) : (
              step.stepNumber
            )}
          </div>
          {!isLast && <div className={styles.stepLine} />}
        </div>

        {/* Step content */}
        <div className={styles.stepBody}>
          {/* Thinking section */}
          {step.thinking && (
            <div className={styles.thinkingSection}>
              <div className={styles.sectionHeader}>
                <ThunderboltOutlined className={styles.thinkingIcon} />
                <span>思考</span>
                {step.thinkingDuration && (
                  <Text type="secondary" className={styles.duration}>
                    {formatDuration(step.thinkingDuration)}
                  </Text>
                )}
                {isThinking && <Spin size="small" className={styles.thinkingSpinner} />}
              </div>
              <div className={styles.thinkingText}>
                {step.thinking}
              </div>
            </div>
          )}

          {/* Action section */}
          {step.action && (
            <div className={styles.actionSection}>
              <div className={styles.sectionHeader}>
                <PlayCircleOutlined className={styles.actionIcon} />
                <span>操作</span>
                {step.actionDuration && (
                  <Text type="secondary" className={styles.duration}>
                    {formatDuration(step.actionDuration)}
                  </Text>
                )}
              </div>
              <div className={styles.actionBody}>
                <Tag
                  color={actionType === 'finish' ? 'green' : 'blue'}
                  className={styles.actionTag}
                >
                  {actionType as string}
                </Tag>
                {renderActionDetails(step.action)}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderAssistantMessage = (message: Message) => {
    const isStreaming = message.isStreaming;
    const steps = message.steps || [];
    const hasSteps = steps.length > 0;

    return (
      <div key={message.id} className={styles.messageRow}>
        <div className={styles.assistantMessage}>
          <Avatar 
            icon={<RobotOutlined />} 
            size={32}
            className={styles.assistantAvatar}
          />
          <div className={styles.assistantContent}>
            {/* Steps timeline */}
            {hasSteps && (
              <div className={styles.stepsContainer}>
                {steps.map((step, index) => renderStep(step, index === steps.length - 1))}
              </div>
            )}

            {/* Loading state when no steps yet */}
            {isStreaming && !hasSteps && (
              <div className={styles.loadingState}>
                <Spin indicator={<LoadingOutlined spin />} size="small" />
                <Text type="secondary">正在连接...</Text>
              </div>
            )}

            {/* Completion message */}
            {!isStreaming && message.content && (
              <div className={`${styles.completionMessage} ${
                message.content.includes('停止') || message.content.includes('取消') 
                  ? styles.stopped 
                  : message.content.includes('错误') 
                    ? styles.error 
                    : ''
              }`}>
                {message.content.includes('停止') || message.content.includes('取消') ? (
                  <StopOutlined className={styles.stoppedIcon} />
                ) : message.content.includes('错误') ? (
                  <StopOutlined className={styles.errorIcon} />
                ) : (
                  <CheckCircleOutlined className={styles.completionIcon} />
                )}
                <Text>{message.content}</Text>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderMessage = (message: Message) => {
    return message.role === 'user' 
      ? renderUserMessage(message) 
      : renderAssistantMessage(message);
  };

  return (
    <div className={styles.container}>
      <div className={styles.messages}>
        {messages.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIconWrapper}>
              <img src="/logo.png" alt="Remote GUI Automation" className={styles.emptyLogo} />
            </div>
            <Text className={styles.emptyTitle}>
              {currentSession ? 'Remote GUI Automation 已就绪' : '欢迎使用 Remote GUI Automation'}
            </Text>
            <Text type="secondary" className={styles.emptyHint}>
              {currentSession
                ? '输入任务开始自动化操作'
                : '请先创建一个会话'}
            </Text>
          </div>
        ) : (
          <>
            {messages.map(renderMessage)}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className={styles.inputArea}>
        {isProcessing ? (
          <div className={styles.processingBar}>
            <div className={styles.processingInfo}>
              <Spin indicator={<LoadingOutlined spin />} size="small" />
              <Text className={styles.processingText}>Agent 正在执行任务...</Text>
            </div>
            <Text type="warning" className={styles.processingWarning}>
              ⚠️ 请勿刷新页面或切换会话，否则任务将终止
            </Text>
            <Button
              type="primary"
              danger
              icon={<StopOutlined />}
              onClick={stopTask}
              className={styles.stopButton}
            >
              停止
            </Button>
          </div>
        ) : (
          <Sender
            placeholder={
              currentSession
                ? '输入任务，例如：打开相册查看最近的照片'
                : '请先创建会话'
            }
            onSubmit={handleSend}
            disabled={!currentSession}
            className={styles.sender}
          />
        )}
      </div>
    </div>
  );
}
