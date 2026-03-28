import {
    getConfiguredAnalysisMode,
} from '../domain/modelSelectionLogic';
import { WorkflowDeps } from './sessionWorkflowController';

export async function cmdSelectModel(deps: WorkflowDeps): Promise<void> {
    try {
        await deps.ensureServer();
        const client = deps.getApiClient();
        const config = await client.getConfig();
        const extConfig = deps.ui.getExtensionConfig();
        const writableConfig = extConfig as any;
        const configuredMode = getConfiguredAnalysisMode(extConfig);
        const availableModes = config.analysis_modes && config.analysis_modes.length > 0
            ? config.analysis_modes
            : ['quick', 'deep'];
        const availableModels = config.available_models || {};

        const modeDescriptions: Record<string, string> = {
            quick: 'Code checks + 7 lenses with quick checker model',
            deep: 'Code checks + 7 lenses with deep checker model',
        };

        const currentSlots = config.model_slots || config.default_model_slots || {
            frontier: 'sonnet',
            deep: 'sonnet',
            quick: 'haiku',
        };

        const getConfiguredSlotValue = (key: 'modelSlotFrontier' | 'modelSlotDeep' | 'modelSlotQuick'): string => {
            const raw = (extConfig.get<string>(key, '') || '').trim();
            if (raw) { return raw; }
            if (key === 'modelSlotFrontier') { return currentSlots.frontier; }
            if (key === 'modelSlotDeep') { return currentSlots.deep; }
            return currentSlots.quick;
        };

        const getConfiguredSlotRaw = (key: 'modelSlotFrontier' | 'modelSlotDeep' | 'modelSlotQuick'): string => {
            return (extConfig.get<string>(key, '') || '').trim();
        };

        const getModelDisplay = (modelKey: string | undefined): string => {
            if (!modelKey) { return 'unknown'; }
            const meta = availableModels[modelKey];
            if (meta?.label) { return `${meta.label} (${modelKey})`; }
            return modelKey;
        };

        const slotKeyToLabel: Record<'modelSlotFrontier' | 'modelSlotDeep' | 'modelSlotQuick', string> = {
            modelSlotFrontier: 'Frontier',
            modelSlotDeep: 'Deep',
            modelSlotQuick: 'Quick',
        };

        const slotOptions = [
            { action: 'modelSlotFrontier' as const, label: 'Set Frontier model slot' },
            { action: 'modelSlotDeep' as const, label: 'Set Deep model slot' },
            { action: 'modelSlotQuick' as const, label: 'Set Quick model slot' },
        ];

        const actionItems = [
            {
                action: 'analysisMode' as const,
                label: 'Set analysis mode',
                description: `Current: ${configuredMode}`,
            },
            ...slotOptions.map((slot) => {
                const raw = getConfiguredSlotRaw(slot.action);
                const effective = getConfiguredSlotValue(slot.action);
                const source = raw ? 'Override' : 'Backend default';
                return {
                    action: slot.action,
                    label: slot.label,
                    description: `${source}: ${getModelDisplay(effective)}`,
                };
            }),
        ];

        const selectedAction = await deps.ui.showQuickPick(actionItems, {
            placeHolder: 'Select setting to configure',
        });

        if (!selectedAction) { return; }

        const selectedActionKey = (typeof selectedAction === 'string'
            ? selectedAction
            : selectedAction.action) as 'analysisMode' | 'modelSlotFrontier' | 'modelSlotDeep' | 'modelSlotQuick';

        if (selectedActionKey === 'analysisMode') {
            const items = availableModes.map((modeName) => ({
                label: modeName,
                description: modeDescriptions[modeName] || undefined,
                detail: modeName === configuredMode ? 'Current mode' : undefined,
            }));

            const selected = await deps.ui.showQuickPick(items, {
                placeHolder: 'Select analysis mode',
                activeItemLabel: configuredMode,
            });

            if (selected) {
                const label = typeof selected === 'string' ? selected : selected.label;
                if (typeof writableConfig.update === 'function') {
                    await writableConfig.update('analysisMode', label, 2 /* Workspace */);
                }
                void deps.ui.showInformationMessage(`lit-critic: Analysis mode set to ${label}`);
            }
            return;
        }

        const modelEntries = Object.entries(availableModels);
        if (modelEntries.length === 0) {
            void deps.ui.showErrorMessage('lit-critic: No models available from server config.');
            return;
        }

        const slotLabel = slotKeyToLabel[selectedActionKey];
        const backendDefault =
            selectedActionKey === 'modelSlotFrontier'
                ? currentSlots.frontier
                : selectedActionKey === 'modelSlotDeep'
                    ? currentSlots.deep
                    : currentSlots.quick;

        const modelItems = [
            {
                label: 'Use backend default',
                description: getModelDisplay(backendDefault),
                value: '',
            },
            ...modelEntries.map(([modelKey, modelMeta]) => ({
                label: modelMeta.label ? `${modelMeta.label} (${modelKey})` : modelKey,
                description: modelMeta.provider ? `Provider: ${modelMeta.provider}` : undefined,
                value: modelKey,
            })),
        ];

        const currentRaw = getConfiguredSlotRaw(selectedActionKey);
        const activeItemLabel = currentRaw ? getModelDisplay(currentRaw) : 'Use backend default';

        const selectedModel = await deps.ui.showQuickPick(modelItems, {
            placeHolder: `Select model for ${slotLabel} slot`,
            activeItemLabel,
        });

        if (!selectedModel) { return; }

        const nextValue = typeof selectedModel === 'string' ? selectedModel : selectedModel.value;
        if (typeof writableConfig.update === 'function') {
            await writableConfig.update(selectedActionKey, nextValue, 2 /* Workspace */);
        }

        if (!nextValue) {
            void deps.ui.showInformationMessage(
                `lit-critic: ${slotLabel} slot set to backend default (${getModelDisplay(backendDefault)}).`,
            );
            return;
        }

        void deps.ui.showInformationMessage(
            `lit-critic: ${slotLabel} slot set to ${getModelDisplay(nextValue)}.`,
        );
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        void deps.ui.showErrorMessage(`lit-critic: ${msg}`);
    }
}
