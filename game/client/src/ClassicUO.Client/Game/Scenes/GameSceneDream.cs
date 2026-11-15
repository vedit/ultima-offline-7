// SPDX-License-Identifier: BSD-2-Clause
using System;
using ClassicUO.Input;
namespace ClassicUO.Game.Scenes
{
    internal partial class GameScene
    {
        protected void ClearDreamInput()
        {
            Array.Clear(_flags,0,_flags.Length);
            _rightMousePressed=false;_continueRunning=false;
            Mouse.ButtonRelease(MouseButtonType.Right);
        }
        protected void BeginDreamMouse() { _rightMousePressed=true; }
    }
}
