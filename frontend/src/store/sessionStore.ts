/**
 * Session and chat state management using Zustand.
 */

import { create } from 'zustand';
import { sessionsApi, agentApi, runTaskWithSSE } from '../services/api';
import type { Session, Message, TakeoverState, AgentStep, AgentType } from '../types';

interface SessionState {
  // Session state
  sessions: Session[];
  currentSession: Session | null;
  isCreatingSession: boolean;

  // Agent selection
  selectedAgentType: AgentType;

  // Chat state
  messages: Message[];
  isProcessing: boolean;

  // Screenshot state
  screenshot: {
    base64: string;
    width: number;
    height: number;
  } | null;

  // Takeover state
  takeover: TakeoverState;

  // SSE abort controller (replaces WebSocket)
  sseController: AbortController | null;

  // Actions
  setAgentType: (agentType: AgentType) => void;
  fetchSessions: () => Promise<void>;
  createSession: (name?: string) => Promise<Session>;
  selectSession: (session: Session) => Promise<void>;
  closeSession: (sessionId: string) => Promise<void>;

  sendTask: (task: string) => Promise<void>;
  stopTask: () => Promise<void>;
  addMessage: (message: Message) => void;
  updateLastMessage: (updates: Partial<Message>) => void;

  completeTakeover: () => Promise<void>;
  clearMessages: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSession: null,
  isCreatingSession: false,
  selectedAgentType: 'glm',
  messages: [],
  isProcessing: false,
  screenshot: null,
  takeover: { isActive: false },
  sseController: null,

  setAgentType: (agentType: AgentType) => {
    set({ selectedAgentType: agentType });
  },

  fetchSessions: async () => {
    try {
      const sessions = await sessionsApi.list();
      set({ sessions });
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  },

  createSession: async (name?: string) => {
    try {
      set({ isCreatingSession: true });

      // Abort existing SSE connection if any
      const { sseController, selectedAgentType } = get();
      if (sseController) {
        sseController.abort();
      }

      // Create session with selected agent type
      const session = await sessionsApi.create(name, selectedAgentType);

      // Clear old messages and set new session
      set((state) => ({
        sessions: [session, ...state.sessions],
        currentSession: session,
        messages: [],
        screenshot: null,
        isProcessing: false,
        takeover: { isActive: false },
        sseController: null,
      }));

      return session;
    } finally {
      set({ isCreatingSession: false });
    }
  },

  selectSession: async (session) => {
    // Abort existing SSE connection
    const { sseController } = get();
    if (sseController) {
      sseController.abort();
    }

    // Set session and clear current state, also update agent type based on session
    set({
      currentSession: session,
      messages: [],
      screenshot: null,
      isProcessing: false,
      selectedAgentType: session.agent_type || 'glm',
      sseController: null,
    });

    // Load conversation history from database
    try {
      const { conversations } = await sessionsApi.getConversations(session.id);

      // Convert database records to Message format
      const messages: Message[] = conversations.map((conv) => {
        const message: Message = {
          id: conv.id,
          role: conv.role as 'user' | 'assistant',
          content: conv.content,
          timestamp: new Date(conv.created_at),
          isStreaming: false,
        };

        // For assistant messages, parse steps from action field
        if (conv.role === 'assistant') {
          // Check if action contains steps array (new format)
          const actionData = conv.action as Record<string, unknown> | null;
          if (actionData?.steps && Array.isArray(actionData.steps)) {
            // New format: steps are stored in action.steps
            message.steps = (actionData.steps as Array<{
              stepNumber: number;
              thinking?: string;
              action?: Record<string, unknown>;
              status: string;
            }>).map((step, index) => ({
              id: `${conv.id}-step-${index + 1}`,
              stepNumber: step.stepNumber || index + 1,
              thinking: step.thinking,
              action: step.action,
              status: (step.status || 'completed') as 'thinking' | 'acting' | 'completed' | 'error',
              timestamp: new Date(conv.created_at),
            }));
          } else if (conv.thinking || conv.action) {
            // Legacy format: single thinking/action pair
            message.steps = [{
              id: `${conv.id}-step-1`,
              stepNumber: 1,
              thinking: conv.thinking as string | undefined,
              action: conv.action as Record<string, unknown> | undefined,
              status: 'completed',
              timestamp: new Date(conv.created_at),
            }];
          }
        }

        return message;
      });

      set({ messages });
    } catch (error) {
      console.error('Failed to load conversation history:', error);
    }
  },

  closeSession: async (sessionId: string) => {
    try {
      await sessionsApi.delete(sessionId);

      const { currentSession, sseController } = get();
      if (currentSession?.id === sessionId) {
        if (sseController) sseController.abort();
        set({ currentSession: null, sseController: null, messages: [], screenshot: null });
      }

      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== sessionId),
      }));
    } catch (error) {
      console.error('Failed to close session:', error);
      throw error;
    }
  },

  sendTask: async (task: string) => {
    const { currentSession, isProcessing, selectedAgentType } = get();

    // Check if already processing
    if (isProcessing) {
      console.warn('Already processing a task');
      return;
    }

    if (!currentSession) {
      console.error('No active session');
      return;
    }

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: task,
      timestamp: new Date(),
    };

    // Add assistant message placeholder with empty steps array
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      steps: [],
      isStreaming: true,
      timestamp: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      isProcessing: true,
    }));

    try {
      // Start SSE connection for task
      const controller = await runTaskWithSSE(
        currentSession.id,
        task,
        {
          onReady: (data) => {
            console.log('SSE ready:', data);
          },

          onThinking: (data) => {
            // Add or update current step with thinking content
            const messages = get().messages;
            const lastMessage = messages[messages.length - 1];
            const steps = lastMessage?.steps || [];

            const lastStep = steps[steps.length - 1];
            const thinkingContent = data.full || data.chunk || '';

            if (!lastStep || lastStep.status === 'completed') {
              // Create new step
              const newStep: AgentStep = {
                id: `step-${Date.now()}`,
                stepNumber: steps.length + 1,
                thinking: thinkingContent,
                thinkingDuration: data.duration,
                status: 'thinking',
                timestamp: new Date(),
              };
              get().updateLastMessage({
                steps: [...steps, newStep],
              });
            } else {
              // Update existing step's thinking
              const updatedSteps = [...steps];
              updatedSteps[updatedSteps.length - 1] = {
                ...lastStep,
                thinking: thinkingContent,
                thinkingDuration: data.duration,
                status: 'thinking',
              };
              get().updateLastMessage({
                steps: updatedSteps,
              });
            }
          },

          onAction: (data) => {
            // Update current step with action and mark as completed
            const messages = get().messages;
            const lastMessage = messages[messages.length - 1];
            const steps = lastMessage?.steps || [];

            if (steps.length > 0) {
              const updatedSteps = [...steps];
              const lastStep = updatedSteps[updatedSteps.length - 1];
              updatedSteps[updatedSteps.length - 1] = {
                ...lastStep,
                action: data.action,
                actionDuration: data.duration,
                status: 'completed',
              };
              get().updateLastMessage({
                steps: updatedSteps,
                action: data.action,
              });
            }
          },

          onScreenshot: (data) => {
            set({
              screenshot: {
                base64: data.base64,
                width: data.width,
                height: data.height,
              }
            });
          },

          onTakeover: (data) => {
            set({
              takeover: {
                isActive: true,
                message: data.message,
              },
            });
          },

          onCompleted: (data) => {
            get().updateLastMessage({
              content: data.message || '任务完成',
              isStreaming: false,
            });
            set({ isProcessing: false, sseController: null });
          },

          onError: (data) => {
            console.error('SSE error:', data);
            const messages = get().messages;
            if (messages.length > 0 && messages[messages.length - 1].isStreaming) {
              get().updateLastMessage({
                content: `错误: ${data.message}`,
                isStreaming: false,
              });
            }
            set({ isProcessing: false, sseController: null });
          },

          onStopped: (data) => {
            get().updateLastMessage({
              content: data.message || '任务已停止',
              isStreaming: false,
            });
            set({ isProcessing: false, sseController: null });
          },

          onConnectionError: (error) => {
            console.error('SSE connection error:', error);
            const messages = get().messages;
            
            // Extract error message from ApiError or use default
            let errorMessage = '连接错误，请重试';
            if (error && typeof error === 'object') {
              // Check for ApiError with status 503 (session expired)
              const apiError = error as { status?: number; message?: string };
              if (apiError.status === 503) {
                errorMessage = apiError.message || '设备连接已断开，请关闭此会话并创建新会话';
              } else if (apiError.message) {
                errorMessage = apiError.message;
              }
            }
            
            if (messages.length > 0 && messages[messages.length - 1].isStreaming) {
              get().updateLastMessage({
                content: errorMessage,
                isStreaming: false,
              });
            }
            set({ isProcessing: false, sseController: null });
          },
        },
        selectedAgentType
      );

      set({ sseController: controller });
    } catch (error) {
      console.error('Failed to send task:', error);
      set({ isProcessing: false });
      get().updateLastMessage({
        content: '发送失败，请重试',
        isStreaming: false,
      });
    }
  },

  stopTask: async () => {
    const { currentSession, isProcessing, sseController } = get();

    if (!isProcessing) {
      console.warn('No task is currently processing');
      return;
    }

    if (!currentSession) {
      console.error('No active session');
      return;
    }

    try {
      // Send stop request to backend
      await agentApi.stopTask(currentSession.id);
      console.log('Stop signal sent');

      // Abort SSE connection
      if (sseController) {
        sseController.abort();
      }

      // Update UI immediately after successful stop
      // Don't rely on SSE callback since we just aborted the connection
      get().updateLastMessage({
        content: '任务已停止',
        isStreaming: false,
      });
      set({ isProcessing: false, sseController: null });
    } catch (error) {
      console.error('Failed to send stop signal:', error);
      // Still update UI
      get().updateLastMessage({
        content: '任务已取消',
        isStreaming: false,
      });
      set({ isProcessing: false, sseController: null });
    }
  },

  addMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  updateLastMessage: (updates: Partial<Message>) => {
    set((state) => {
      const messages = [...state.messages];
      const lastIndex = messages.length - 1;
      if (lastIndex >= 0) {
        messages[lastIndex] = { ...messages[lastIndex], ...updates };
      }
      return { messages };
    });
  },

  completeTakeover: async () => {
    const { currentSession } = get();
    if (currentSession) {
      try {
        await agentApi.completeTakeover(currentSession.id);
      } catch (error) {
        console.error('Failed to complete takeover:', error);
      }
    }
    set({ takeover: { isActive: false } });
  },

  clearMessages: () => {
    set({ messages: [] });
  },
}));
