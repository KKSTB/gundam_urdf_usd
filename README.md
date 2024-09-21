# isaac_lab_gundam_usd
USD files cnverted and edited from isaac_lab_gundam_robot_urdf, to be used by IsaacLabGundam

Files:
1. usd/GGC_TestModel_rx78_20170112_10.usd: a 1:10 model of RX-78, with fixed mimic joints (due to crashes during isaac lab training), reduced joint effort limit, and zero joint damping and friction
3. scripts/export_utils.py: edited export_utils.py in $HOME/.local/share/ov/pkg/isaac-sim-4.2.0/extscache/omni.kit.widget.stage-2.11.2+10a4b5c0/omni/kit/widget/stage/, so that prims are in the correct prim path (https://forums.developer.nvidia.com/t/export-usd-model-from-usd-composer-isaac-sim/258436)
